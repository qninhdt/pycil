"""Score/state engine (apply_checkpoint_result) against real Postgres + fakeredis.

Covers acceptance #2-6 and invariants #13/#14: at most one FSRS update per
(session, sense), Again on first disqualifier, Good on clean completion, fallback
locks Again, repair adds no second FSRS, acquisition new->scheduled.
"""

import uuid
from datetime import UTC, datetime

import pytest
from lexi_ai.contracts import ChoiceReveal
from redis.exceptions import RedisError
from sqlalchemy import select

from pycil.auth.models import User
from pycil.db.redis import get_redis
from pycil.learning import service, session_store
from pycil.learning.models import GradeStatus, Response, ReviewLog, SenseStatus, UserSenseStats
from pycil.learning.session_store import AdmittedSense

pytestmark = pytest.mark.asyncio


async def _user(session) -> User:
    user = User(email=f"engine-{uuid.uuid4().hex[:8]}@x.co")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _start(redis, user, sense_id, purpose, levels):
    sid = uuid.uuid4().hex
    await session_store.create(
        redis, sid, owner_id=user.id, node_id=uuid.uuid4(), scope_generation=1,
        target_words=1, max_per_round=4,
        admitted=[AdmittedSense(sense_id, purpose, levels)],
    )
    return sid


async def _answer(session, redis, user, sid, sense_id, qid, requested, served, verdict):
    """Simulate a delivered+graded checkpoint through the engine."""
    response = Response(
        user_id=user.id, session_id=sid, sense_id=sense_id, question_id=qid,
        requested_level=requested, served_level=served, raw_answer=None,
        idempotency_key=f"{sid}:{qid}",
    )
    session.add(response)
    await session.flush()
    return await service.apply_checkpoint_result(
        session, redis, response=response, verdict=verdict, score=1.0 if verdict else 0.0,
        feedback=None,
        now=datetime.now(UTC),
        reveal=ChoiceReveal(correct_index=0, correct_option="answer"),
    )


async def _review_logs(session, user):
    rows = await session.execute(select(ReviewLog).where(ReviewLog.user_id == user.id))
    return rows.scalars().all()


async def test_acquisition_enters_fsrs_after_n_checkpoints(session):
    redis = get_redis()
    user = await _user(session)
    sid = await _start(redis, user, 42, "new", [1, 1])
    await session_store.set_exposed(redis, sid, 42)

    out0 = await _answer(session, redis, user, sid, 42, 100, 1, 1, True)
    assert out0.fsrs_applied is False  # not complete yet
    out1 = await _answer(session, redis, user, sid, 42, 101, 1, 1, True)
    assert out1.fsrs_applied is True and out1.applied_grade == "good"

    stats = await session.get(UserSenseStats, (user.id, 42))
    assert stats.status == SenseStatus.scheduled and stats.review_count == 1
    logs = await _review_logs(session, user)
    assert len(logs) == 1 and logs[0].grade == 3


async def test_scheduled_review_clean_run_one_good(session):
    redis = get_redis()
    user = await _user(session)
    sid = await _start(redis, user, 55, "due", [2, 2])
    await _answer(session, redis, user, sid, 55, 200, 2, 2, True)
    out = await _answer(session, redis, user, sid, 55, 201, 2, 2, True)
    assert out.applied_grade == "good"
    logs = await _review_logs(session, user)
    assert len(logs) == 1 and logs[0].grade == 3


async def test_first_wrong_locks_again_repair_adds_no_second_fsrs(session):
    redis = get_redis()
    user = await _user(session)
    sid = await _start(redis, user, 66, "due", [2, 2])
    wrong = await _answer(session, redis, user, sid, 66, 300, 2, 2, False)
    assert wrong.applied_grade == "again" and wrong.state_action == "open_retry"
    assert wrong.reveal is None
    # Retry the same checkpoint correct -> completes it, no new FSRS.
    retry = await _answer(session, redis, user, sid, 66, 301, 2, 2, True)
    assert retry.applied_grade is None and retry.fsrs_applied is False
    # Final checkpoint correct -> completes N, but claim consumed -> no Good.
    final = await _answer(session, redis, user, sid, 66, 302, 2, 2, True)
    assert final.fsrs_applied is False
    logs = await _review_logs(session, user)
    assert len(logs) == 1 and logs[0].grade == 1  # exactly one Again


async def test_fallback_locks_again(session):
    redis = get_redis()
    user = await _user(session)
    sid = await _start(redis, user, 77, "due", [3, 3])
    # Served level 1 below requested 3 -> fallback disqualifier, even if correct.
    out = await _answer(session, redis, user, sid, 77, 400, 3, 1, True)
    assert out.applied_grade == "again" and out.state_action == "complete"
    logs = await _review_logs(session, user)
    assert len(logs) == 1 and logs[0].grade == 1


async def test_repeated_wrong_is_bounded(session):
    redis = get_redis()
    user = await _user(session)
    sid = await _start(redis, user, 88, "due", [2, 2])
    outcomes = []
    for qid in (500, 501, 502):
        outcomes.append(await _answer(session, redis, user, sid, 88, qid, 2, 2, False))
    assert [outcome.reveal for outcome in outcomes[:2]] == [None, None]
    assert outcomes[-1].reveal == {"correct_index": 0, "correct_option": "answer"}
    progress = await session_store.get_progress(redis, sid, 88)
    assert progress.terminal is True and progress.terminal_reason == "retries_exhausted"
    logs = await _review_logs(session, user)
    assert len(logs) == 1  # only the first disqualifier applied FSRS



async def test_redis_projection_failure_does_not_undo_committed_grade(session, monkeypatch):
    redis = get_redis()
    user = await _user(session)
    sid = await _start(redis, user, 99, "due", [2, 2])

    async def fail_projection(*_args, **_kwargs):
        raise RedisError("redis unavailable after commit")

    monkeypatch.setattr(session_store, "apply_checkpoint_projection", fail_projection)
    outcome = await _answer(session, redis, user, sid, 99, 600, 2, 2, True)

    response = await session.get(Response, outcome.response_id)
    assert outcome.is_correct is True
    assert response.grade_status == GradeStatus.graded
    assert response.render_format == "free_text"
    assert response.reveal == {"correct_index": 0, "correct_option": "answer"}
