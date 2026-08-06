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
from pycil.hierarchy.application import service as hierarchy_service
from pycil.hierarchy.infra.models import NodeType
from pycil.learning.application import service
from pycil.learning.infra import session_store
from pycil.learning.infra.models import (
    GradeStatus,
    Response,
    ReviewLog,
    SenseStatus,
    UserSenseStats,
)
from pycil.learning.infra.session_store import AdmittedSense

pytestmark = pytest.mark.asyncio


async def _user(session) -> User:
    user = User(email=f"engine-{uuid.uuid4().hex[:8]}@x.co")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _deck(session, owner_id):
    """A real deck row.

    `ReviewLog.node_id` is a foreign key to `nodes.id` (SET NULL on delete), so a
    session created with a fabricated `node_id` now fails the insert instead of
    silently writing NULL. Tests that drive `apply_checkpoint_result` therefore need
    a node that exists.
    """
    node = await hierarchy_service.create_node(
        session, owner_id, node_type=NodeType.DECK, name=f"deck-{uuid.uuid4().hex[:6]}"
    )
    return node.id


async def _start(session, redis, user, sense_id, purpose, levels):
    sid = uuid.uuid4().hex
    await session_store.create(
        redis, sid, owner_id=user.id, node_id=await _deck(session, user.id),
        scope_generation=1, target_words=1, max_per_round=4,
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
    sid = await _start(session, redis, user, 42, "new", [1, 1])
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
    sid = await _start(session, redis, user, 55, "due", [2, 2])
    await _answer(session, redis, user, sid, 55, 200, 2, 2, True)
    out = await _answer(session, redis, user, sid, 55, 201, 2, 2, True)
    assert out.applied_grade == "good"
    logs = await _review_logs(session, user)
    assert len(logs) == 1 and logs[0].grade == 3


async def test_first_wrong_locks_again_repair_adds_no_second_fsrs(session):
    redis = get_redis()
    user = await _user(session)
    sid = await _start(session, redis, user, 66, "due", [2, 2])
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
    sid = await _start(session, redis, user, 77, "due", [3, 3])
    # Served level 1 below requested 3 -> fallback disqualifier, even if correct.
    out = await _answer(session, redis, user, sid, 77, 400, 3, 1, True)
    assert out.applied_grade == "again" and out.state_action == "complete"
    logs = await _review_logs(session, user)
    assert len(logs) == 1 and logs[0].grade == 1


async def test_repeated_wrong_is_bounded(session):
    redis = get_redis()
    user = await _user(session)
    sid = await _start(session, redis, user, 88, "due", [2, 2])
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
    sid = await _start(session, redis, user, 99, "due", [2, 2])

    async def fail_projection(*_args, **_kwargs):
        raise RedisError("redis unavailable after commit")

    monkeypatch.setattr(session_store, "apply_checkpoint_projection", fail_projection)
    outcome = await _answer(session, redis, user, sid, 99, 600, 2, 2, True)

    response = await session.get(Response, outcome.response_id)
    assert outcome.is_correct is True
    assert response.grade_status == GradeStatus.graded
    assert response.render_format == "free_text"
    assert response.reveal == {"correct_index": 0, "correct_option": "answer"}


async def test_review_log_records_the_deck_the_review_happened_in(session):
    """B5. `ReviewLog.node_id` must carry the session's deck.

    The column has existed since `models.py:63` and nothing wrote it, so every row
    was NULL and the dashboard's "continue where you left off" query
    (`ReviewLog.node_id.is_not(None)`) never matched. `Response` does not carry the
    deck, so the value has to come from the session's Redis meta.
    """
    redis = get_redis()
    user = await _user(session)
    node_id = await _deck(session, user.id)
    sid = uuid.uuid4().hex
    await session_store.create(
        redis, sid, owner_id=user.id, node_id=node_id, scope_generation=1,
        target_words=1, max_per_round=4,
        admitted=[AdmittedSense(77, "new", [1, 1])],
    )
    await session_store.set_exposed(redis, sid, 77)
    await _answer(session, redis, user, sid, 77, 9001, 1, 1, True)
    await _answer(session, redis, user, sid, 77, 9002, 1, 1, True)

    logs = await _review_logs(session, user)
    assert logs, "a completed checkpoint pair must produce a ReviewLog"
    assert all(row.node_id == node_id for row in logs), (
        f"every ReviewLog must name the session's deck, got {[r.node_id for r in logs]}"
    )


async def test_review_log_survives_an_expired_session_without_a_node(session):
    """The write must not depend on Redis still holding the session meta.

    An LLM settle can land long after the session key expires. `node_id` is
    best-effort for exactly that reason: it degrades to NULL rather than failing a
    grade the learner already paid for. Only the META key is dropped here — dropping
    the whole database would also destroy the checkpoint progress and the grade would
    never come due, which tests the wrong thing.
    """
    redis = get_redis()
    user = await _user(session)
    sid = await _start(session, redis, user, 88, "new", [1, 1])
    await session_store.set_exposed(redis, sid, 88)
    await _answer(session, redis, user, sid, 88, 9101, 1, 1, True)

    assert await session_store.get_meta(redis, sid) is not None
    await redis.delete(session_store._key(sid))
    assert await session_store.get_meta(redis, sid) is None

    await _answer(session, redis, user, sid, 88, 9102, 1, 1, True)

    logs = await _review_logs(session, user)
    assert logs, "the grade must still be recorded when the session meta is gone"
    assert logs[-1].node_id is None, "a missing meta must degrade to NULL, not guess"


async def test_a_hard_deleted_deck_releases_its_review_history(session):
    """The FK is SET NULL, so erasing a deck must not erase or block the history.

    Two properties at once, both previously broken by the NO ACTION default:
    `DELETE FROM nodes` succeeds (account deletion hard-deletes nodes and only
    clears `review_log WHERE user_id = :owner`, so another learner's rows used to
    block it), and the review survives with `node_id` NULL rather than cascading
    away — FSRS history belongs to the learner, not the deck.
    """
    from sqlalchemy import text as sql_text

    redis = get_redis()
    user = await _user(session)
    sid = await _start(session, redis, user, 55, "new", [1, 1])
    await session_store.set_exposed(redis, sid, 55)
    await _answer(session, redis, user, sid, 55, 9201, 1, 1, True)
    await _answer(session, redis, user, sid, 55, 9202, 1, 1, True)

    logs = await _review_logs(session, user)
    assert logs and logs[0].node_id is not None
    doomed = logs[0].node_id

    # `deck_attributes` also references `nodes` with no ON DELETE action — one of
    # the FKs the wider integrity work still has to fix — so clear it first, the
    # same order `account_lifecycle.service` uses. What is under test here is that
    # `review_log` no longer needs that treatment.
    await session.execute(
        sql_text("DELETE FROM deck_attributes WHERE node_id = :id"), {"id": doomed}
    )
    await session.execute(sql_text("DELETE FROM nodes WHERE id = :id"), {"id": doomed})
    await session.commit()

    # Read the columns back directly: the ORM identity map still holds the old
    # `node_id`, and SET NULL happened inside the database rather than through it.
    rows = (
        await session.execute(
            sql_text(
                "SELECT node_id FROM review_log WHERE user_id = :uid ORDER BY id"
            ),
            {"uid": user.id},
        )
    ).all()
    assert len(rows) == len(logs), "the review must outlive its deck"
    assert all(row.node_id is None for row in rows), f"the FK must SET NULL, got {rows}"


async def test_a_lost_claim_with_no_visible_stats_reports_no_transition(session, monkeypatch):
    """B6. Losing the claim before the winner commits must not report 0 -> 0.

    Three variables (`mastery_before`, `mastery_after`, `stability_after`) were
    initialised to zero and only assigned inside `if first:` or
    `elif stats is not None:`. When a submission lost the claim AND no stats row was
    visible — the winner holds the row lock and has not committed — neither branch
    ran, so the response announced `masteryBefore: 0, masteryAfter: 0` for an answer
    that did apply FSRS. Zero is a legitimate mastery, so the client cannot tell that
    reading apart from a real one; it renders as "no progress was made".

    `None` says "unknown from here", which the schema allows and the web client
    already renders as nothing at all.
    """
    redis = get_redis()
    user = await _user(session)
    sid = await _start(session, redis, user, 61, "due", [2, 2])
    await session_store.set_exposed(redis, sid, 61)

    # Force exactly the racing shape: the claim is taken by someone else, and the
    # stats row is not yet visible to this transaction.
    monkeypatch.setattr(service, "_claim_first_attempt", lambda *a, **k: _false())
    monkeypatch.setattr(service, "_lock_stats", lambda *a, **k: _none())

    outcome = await _answer(session, redis, user, sid, 61, 9301, 2, 2, False)

    assert outcome.fsrs_applied is False
    assert outcome.mastery_before is None, (
        f"a lost claim with no stats must not claim a mastery, got "
        f"{outcome.mastery_before}"
    )
    assert outcome.mastery_after is None


async def _false() -> bool:
    return False


async def _none() -> None:
    return None
