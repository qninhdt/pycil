"""Redis session-state CAS: one-shot score lock, checkpoint pass, retry, bind."""

import asyncio
import uuid

import fakeredis.aioredis as fake_aioredis
import pytest

from pycil.learning import session_store
from pycil.learning.session_store import AdmittedSense

pytestmark = pytest.mark.asyncio


async def _make_session(admitted):
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    sid = uuid.uuid4().hex
    await session_store.create(
        redis,
        sid,
        owner_id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        scope_generation=1,
        target_words=3,
        max_per_round=4,
        admitted=admitted,
    )
    return redis, sid


async def test_lock_score_is_one_shot_under_concurrency():
    redis, sid = await _make_session([AdmittedSense(10, "due", [2, 2])])
    results = await asyncio.gather(
        *[session_store.lock_score(redis, sid, 10, "again") for _ in range(8)]
    )
    winners = [r for r in results if r == "again"]
    assert len(winners) == 1
    # A subsequent good lock is refused (already locked).
    assert await session_store.lock_score(redis, sid, 10, "good") is None


async def test_pass_checkpoint_reaches_terminal_at_n():
    redis, sid = await _make_session([AdmittedSense(10, "new", [1, 1])])
    assert await session_store.pass_checkpoint(redis, sid, 10, required_checkpoints=2) == 1
    progress = await session_store.get_progress(redis, sid, 10)
    assert progress.terminal is False
    assert await session_store.pass_checkpoint(redis, sid, 10, required_checkpoints=2) == 2
    progress = await session_store.get_progress(redis, sid, 10)
    assert progress.terminal is True and progress.terminal_reason == "completed"


async def test_open_retry_exhaustion_marks_terminal():
    redis, sid = await _make_session([AdmittedSense(10, "due", [2, 2])])
    await session_store.open_retry(
        redis, sid, 10, requested_level=2, retries_used=3, failed_round=1, max_retries=2
    )
    progress = await session_store.get_progress(redis, sid, 10)
    assert progress.terminal is True and progress.terminal_reason == "retries_exhausted"


async def test_consume_delivered_is_one_shot():
    redis, sid = await _make_session([AdmittedSense(10, "due", [2, 2])])
    await session_store.set_delivered(redis, sid, 10, 555)
    # Wrong id rejected; correct id consumed once.
    assert await session_store.consume_delivered(redis, sid, 10, 999) is False
    assert await session_store.consume_delivered(redis, sid, 10, 555) is True
    assert await session_store.consume_delivered(redis, sid, 10, 555) is False


async def test_excluded_ids_roundtrip_as_int_frozenset():
    redis, sid = await _make_session([AdmittedSense(10, "due", [2, 2])])
    await session_store.add_excluded(redis, sid, 10, 111)
    await session_store.add_excluded(redis, sid, 10, 222)
    excluded = await session_store.excluded_ids(redis, sid, 10)
    assert excluded == frozenset({111, 222})
    assert all(isinstance(x, int) for x in excluded)


async def test_end_session_clears_namespace():
    redis, sid = await _make_session([AdmittedSense(10, "due", [2, 2])])
    await session_store.apply_checkpoint_projection(
        redis, sid, 10, response_id=uuid.uuid4(), state_action="complete",
        requested_level=2, retries_used=0, failed_round=0, max_retries=2,
        grade_due=None, fsrs_applied=False,
    )
    await session_store.end_session(redis, sid)
    assert await session_store.get_meta(redis, sid) is None
    assert await session_store.get_progress(redis, sid, 10) is None
    assert await redis.exists(f"session:{sid}:sense:10:projected") == 0



async def test_round_delivery_reservation_has_one_winner_under_concurrency():
    redis, sid = await _make_session([AdmittedSense(10, "due", [2, 2])])
    current_round = await session_store.advance_round(redis, sid, expected_round=0)
    results = await asyncio.gather(
        *[
            session_store.reserve_round_delivery(
                redis, sid, 10, current_round, question_id=500 + index
            )
            for index in range(8)
        ]
    )
    assert results.count(True) == 1
    meta = await session_store.get_meta(redis, sid)
    assert meta.round_count == 1
    excluded = await session_store.excluded_ids(redis, sid, 10)
    assert len(excluded) == 1


async def test_prepare_attempts_are_cooldown_bounded():
    redis, sid = await _make_session([AdmittedSense(10, "due", [2, 2])])
    assert await session_store.claim_prepare_attempt(redis, sid, now_timestamp=100) == "claimed"
    assert await session_store.claim_prepare_attempt(redis, sid, now_timestamp=101) == "waiting"
    assert await session_store.claim_prepare_attempt(redis, sid, now_timestamp=110) == "claimed"
    assert await session_store.claim_prepare_attempt(redis, sid, now_timestamp=120) == "claimed"
    assert await session_store.claim_prepare_attempt(redis, sid, now_timestamp=121) == "waiting"
    assert await session_store.claim_prepare_attempt(redis, sid, now_timestamp=130) == "exhausted"



async def test_checkpoint_projection_is_atomic_and_idempotent():
    redis, sid = await _make_session([AdmittedSense(10, "due", [2, 2])])
    response_id = uuid.uuid4()
    kwargs = {
        "response_id": response_id,
        "state_action": "complete",
        "requested_level": 2,
        "retries_used": 1,
        "failed_round": 1,
        "max_retries": 2,
        "grade_due": "good",
        "fsrs_applied": True,
    }
    assert await session_store.apply_checkpoint_projection(redis, sid, 10, **kwargs)
    assert await session_store.apply_checkpoint_projection(redis, sid, 10, **kwargs)
    progress = await session_store.get_progress(redis, sid, 10)
    assert progress.passed == 1
    assert progress.score == "good"
    assert progress.fsrs_applied is True



async def test_checkpoint_projection_deduplicates_interleaved_replay():
    redis, sid = await _make_session([AdmittedSense(10, "due", [2, 2, 2])])

    async def project(response_id):
        return await session_store.apply_checkpoint_projection(
            redis, sid, 10, response_id=response_id, state_action="complete",
            requested_level=2, retries_used=1, failed_round=1, max_retries=2,
            grade_due=None, fsrs_applied=False, required_checkpoints=3,
        )

    response_a = uuid.uuid4()
    response_b = uuid.uuid4()
    assert await project(response_a)
    assert await project(response_b)
    assert await project(response_a)
    progress = await session_store.get_progress(redis, sid, 10)
    assert progress.passed == 2
    assert progress.terminal is False


async def test_advance_round_expected_value_prevents_double_advance():
    redis, sid = await _make_session([AdmittedSense(10, "due", [2, 2])])
    rounds = await asyncio.gather(
        *[session_store.advance_round(redis, sid, expected_round=0) for _ in range(8)]
    )
    assert rounds == [1] * 8
    assert await session_store.current_round(redis, sid) == 1
