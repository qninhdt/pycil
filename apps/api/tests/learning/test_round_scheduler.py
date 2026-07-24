"""Round scheduler: priority order, once-per-round, retry-wait, session_complete."""

import uuid

import fakeredis.aioredis as fake_aioredis

from pycil.learning import round_scheduler as sch
from pycil.learning import session_store
from pycil.learning.session_store import AdmittedSense, SenseProgress


def _progress(**overrides) -> SenseProgress:
    base = dict(
        sense_id=1, passed=0, score="none", fsrs_applied=False, exposed=False,
        open_checkpoint=None, retries_used=0, open_requested_level=None,
        open_failed_round=None, awaiting_grade=False, last_round_used=0,
        terminal=False, terminal_reason="", requested_levels=[1, 1],
    )
    base.update(overrides)
    return SenseProgress(**base)


def test_eligibility_tiers():
    assert sch.eligible_requirement("new", _progress(), 1).kind == "exposure"
    r = sch.eligible_requirement("new", _progress(exposed=True), 1)
    assert r.kind == "checkpoint" and r.tier == 3
    r = sch.eligible_requirement("due", _progress(requested_levels=[2, 3]), 1)
    assert r.kind == "checkpoint" and r.tier == 2 and r.requested_level == 2


def test_eligibility_gates():
    assert sch.eligible_requirement("due", _progress(terminal=True), 1) is None
    assert sch.eligible_requirement("due", _progress(awaiting_grade=True), 1) is None
    assert sch.eligible_requirement("due", _progress(last_round_used=3), 3) is None


def test_retry_waits_at_least_one_round():
    # Failed this round -> not eligible same round.
    same = _progress(open_checkpoint=0, open_failed_round=2, open_requested_level=2, retries_used=1)
    assert sch.eligible_requirement("due", same, 2) is None
    # Next round -> eligible retry.
    r = sch.eligible_requirement("due", same, 3)
    assert r is not None and r.is_retry and r.tier == 1


async def _session(admitted):
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    sid = uuid.uuid4().hex
    await session_store.create(
        redis, sid, owner_id=uuid.uuid4(), node_id=uuid.uuid4(), scope_generation=1,
        target_words=3, max_per_round=4, admitted=admitted,
    )
    return redis, sid


async def test_round_candidates_priority_order():
    redis, sid = await _session(
        [
            AdmittedSense(10, "due", [2, 2]),
            AdmittedSense(20, "new", [1, 1]),
            AdmittedSense(30, "new", [1, 1]),
        ]
    )
    await session_store.set_exposed(redis, sid, 30)  # 30 -> acquisition
    cur = await session_store.advance_round(redis, sid)
    candidates = await sch.round_candidates(redis, sid, cur)
    tiers = [(c.tier, c.sense_id) for c in candidates]
    assert tiers == [(2, 10), (3, 30), (4, 20)]  # due -> acquisition -> exposure


async def test_session_complete_requires_all_terminal():
    redis, sid = await _session([AdmittedSense(10, "due", [2, 2])])

    class _NoPendingSession:
        async def scalar(self, *_a, **_k):
            return 0

    fake_session = _NoPendingSession()
    assert await sch.session_complete(fake_session, redis, sid) is False
    # Mark terminal.
    await session_store.open_retry(
        redis, sid, 10, requested_level=2, retries_used=3, failed_round=1
    )
    assert await sch.session_complete(fake_session, redis, sid) is True
