"""Redis session-state CAS: one-shot score lock, checkpoint pass, retry, bind."""

import asyncio
import uuid

import fakeredis.aioredis as fake_aioredis
import pytest

from pycil.learning.infra import session_store
from pycil.learning.infra.session_store import AdmittedSense
from tests.learning import session_state

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


async def test_the_first_grade_settles_the_score_and_a_later_one_cannot_move_it():
    """One-shot ``none -> grade``, asserted on the writer production uses.

    This behaviour used to live in a standalone ``lock_score`` CAS that nothing
    outside the tests called. The projection carries it now (it writes ``score``
    only while the stored value is still ``none``), so the guarantee is asserted
    where it actually runs: a disqualifier settles ``again``, and a later clean
    completion cannot rewrite that to ``good``.
    """
    redis, sid = await _make_session([AdmittedSense(10, "due", [2, 2])])
    common = {
        "requested_level": 2, "retries_used": 0, "failed_round": 0,
        "max_retries": 2, "fsrs_applied": False,
    }

    await session_store.apply_checkpoint_projection(
        redis, sid, 10, response_id=uuid.uuid4(), state_action="complete",
        grade_due="again", **common,
    )
    assert (await session_store.get_progress(redis, sid, 10)).score == "again"

    await session_store.apply_checkpoint_projection(
        redis, sid, 10, response_id=uuid.uuid4(), state_action="complete",
        grade_due="good", **common,
    )
    assert (await session_store.get_progress(redis, sid, 10)).score == "again"


async def test_concurrent_projections_of_one_grade_settle_the_score_once():
    """Eight replays of the same response are one checkpoint, not eight.

    The concurrency half of what the old one-shot lock test covered, but against
    the real replay shape: arq redelivers a job, so the same ``response_id``
    arrives more than once and must project exactly once.
    """
    redis, sid = await _make_session([AdmittedSense(10, "due", [2, 2])])
    response_id = uuid.uuid4()
    kwargs = {
        "response_id": response_id, "state_action": "complete", "requested_level": 2,
        "retries_used": 0, "failed_round": 0, "max_retries": 2, "grade_due": "again",
        "fsrs_applied": False,
    }

    results = await asyncio.gather(
        *[session_store.apply_checkpoint_projection(redis, sid, 10, **kwargs) for _ in range(8)]
    )

    assert all(results)
    progress = await session_store.get_progress(redis, sid, 10)
    assert progress.passed == 1, "a replayed grade must not count as several checkpoints"
    assert progress.score == "again"


async def test_passing_the_required_checkpoints_reaches_terminal():
    redis, sid = await _make_session([AdmittedSense(10, "new", [1, 1])])
    assert await session_state.pass_checkpoint(redis, sid, 10, required_checkpoints=2)
    progress = await session_store.get_progress(redis, sid, 10)
    assert progress.passed == 1 and progress.terminal is False
    assert await session_state.pass_checkpoint(redis, sid, 10, required_checkpoints=2)
    progress = await session_store.get_progress(redis, sid, 10)
    assert progress.terminal is True and progress.terminal_reason == "completed"


async def test_exhausting_the_retry_budget_marks_terminal():
    redis, sid = await _make_session([AdmittedSense(10, "due", [2, 2])])
    await session_state.open_retry(
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
    await session_state.exclude_question(redis, sid, 10, 111)
    await session_state.exclude_question(redis, sid, 10, 222)
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


async def test_a_taken_slot_always_carries_a_ttl():
    """B10. The quota key must never be left without an expiry.

    `INCR` then `EXPIRE` as two round trips means a process that dies between them
    leaves a counter that never decays — so a 5-minute window becomes a permanent
    lockout from LLM grading. One Lua script makes the pair atomic.
    """
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    owner = uuid.uuid4()

    assert await session_store.take_grading_slot(redis, owner, limit=2) is True

    ttl = await redis.ttl(f"session:grading-quota:{owner}")
    assert ttl > 0, f"the key must expire on its own, got ttl={ttl}"

    # A second increment must not re-arm the window, or a steady stream of requests
    # would hold the key open indefinitely.
    assert await session_store.take_grading_slot(redis, owner, limit=2) is True
    assert await redis.ttl(f"session:grading-quota:{owner}") <= ttl


async def test_the_slot_limit_still_rejects_past_the_budget():
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    owner = uuid.uuid4()
    verdicts = [
        await session_store.take_grading_slot(redis, owner, limit=3) for _ in range(5)
    ]
    assert verdicts == [True, True, True, False, False]


async def test_releasing_an_unspent_slot_gives_the_budget_back():
    """A slot charged before a durable write that then failed must be returned.

    Without this the learner has paid for a grade that never happened and cannot
    retry until the window rolls.
    """
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    owner = uuid.uuid4()
    key = f"session:grading-quota:{owner}"

    await session_store.take_grading_slot(redis, owner, limit=1)
    await session_store.take_grading_slot(redis, owner, limit=1)
    assert int(await redis.get(key)) == 2

    await session_store.release_grading_slot(redis, owner)
    assert int(await redis.get(key)) == 1

    # The last release removes the key rather than leaving a 0 with a TTL.
    await session_store.release_grading_slot(redis, owner)
    assert await redis.get(key) is None
    assert await session_store.take_grading_slot(redis, owner, limit=1) is True


async def test_releasing_a_slot_never_raises():
    """It runs on an error path, so it must not replace the caller's exception."""

    class Broken:
        async def eval(self, *_args):
            raise RuntimeError("redis is down")

    await session_store.release_grading_slot(Broken(), uuid.uuid4())


async def test_advancing_a_dead_session_does_not_resurrect_it():
    """B15. `advance_round` must not recreate a session that has expired.

    `HSET` creates a missing key, so an expired session was silently reborn as a hash
    holding only `round_index` — no owner, no node. `get_meta` then indexed straight
    into `raw["owner"]` and raised `KeyError`, turning an expired session into a 500
    instead of the `session_not_found` the caller expects.
    """
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    gone = uuid.uuid4().hex

    assert await session_store.advance_round(redis, gone, expected_round=0) == 0
    assert [key async for key in redis.scan_iter(match="*")] == [], (
        "no key may be created for a session that no longer exists"
    )
    assert await session_store.get_meta(redis, gone) is None


async def test_get_meta_treats_a_partial_hash_as_absent():
    """Defence in depth for the same shape, whatever produced it."""
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    sid = uuid.uuid4().hex
    await redis.hset(f"session:{sid}", mapping={"round_index": "3", "round_count": "0"})

    assert await session_store.get_meta(redis, sid) is None


async def test_advancing_a_live_session_still_increments():
    """The guard must not break the ordinary path."""
    redis, sid = await _make_session([AdmittedSense(1, "new", [1, 1])])

    assert await session_store.current_round(redis, sid) == 0
    assert await session_store.advance_round(redis, sid, expected_round=0) == 1
    assert await session_store.advance_round(redis, sid, expected_round=1) == 2
    meta = await session_store.get_meta(redis, sid)
    assert meta is not None and meta.round_index == 2

    # A mismatched expectation is still a no-op that reports the truth.
    assert await session_store.advance_round(redis, sid, expected_round=99) == 2
