"""An aborted answer must not strand a sense for the rest of the session.

``restore_delivered`` used to re-arm ``current_qid`` with the same question id and
stop. ``reserve_round_delivery`` refuses any sense whose ``current_qid`` is not
``_MISSING``, so once an answer aborted, that sense could never be delivered again
in any round — the only escape was the client resubmitting the exact same question
id, and if the question had been purged in Lexi there was no escape at all. The
session could then poll ``/next`` forever without reaching ``exhausted``.
"""

import uuid

import fakeredis.aioredis as fake_aioredis
import pytest

from pycil.learning import session_store
from pycil.learning.session_store import AdmittedSense

pytestmark = pytest.mark.asyncio

_SENSE = 10
_OTHER_SENSE = 20
_QID = 555


async def _session(admitted=None, *, max_per_round=4):
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    sid = uuid.uuid4().hex
    await session_store.create(
        redis,
        sid,
        owner_id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        scope_generation=1,
        target_words=3,
        max_per_round=max_per_round,
        admitted=admitted or [AdmittedSense(_SENSE, "due", [2, 2])],
    )
    # Round 0 is the pre-first-round state; deliveries happen from round 1 on.
    await session_store.advance_round(redis, sid, expected_round=0)
    return redis, sid


async def _deliver(redis, sid, sense_id=_SENSE, qid=_QID):
    round_index = await session_store.current_round(redis, sid)
    reserved = await session_store.reserve_round_delivery(
        redis, sid, sense_id, round_index, question_id=qid
    )
    assert reserved is True
    return round_index


async def test_the_wedge_is_gone_sense_is_deliverable_again():
    redis, sid = await _session()
    await _deliver(redis, sid)

    # The answer aborts before any durable row is written.
    await session_store.restore_delivered(redis, sid, _SENSE, _QID)

    progress = await session_store.get_progress(redis, sid, _SENSE)
    assert progress.last_round_used < await session_store.current_round(redis, sid)
    # And the same checkpoint can be re-served immediately, in the SAME round.
    assert await _deliver(redis, sid) == await session_store.current_round(redis, sid)


async def test_reopen_clears_the_bind_and_the_exclusion():
    redis, sid = await _session()
    await _deliver(redis, sid)
    assert await session_store.excluded_ids(redis, sid, _SENSE) == frozenset({_QID})

    await session_store.restore_delivered(redis, sid, _SENSE, _QID)

    # The question is re-servable rather than burned: the learner gets the question
    # they were on, not a different one.
    assert await session_store.excluded_ids(redis, sid, _SENSE) == frozenset()
    assert await session_store.get_delivered(redis, sid, _SENSE) is None


async def test_sense_survives_across_a_round_boundary_after_an_abort():
    redis, sid = await _session()
    await _deliver(redis, sid)
    await session_store.restore_delivered(redis, sid, _SENSE, _QID)

    before = await session_store.current_round(redis, sid)
    after = await session_store.advance_round(redis, sid, expected_round=before)
    assert after == before + 1

    assert await session_store.reserve_round_delivery(
        redis, sid, _SENSE, after, question_id=_QID
    )


async def test_repeated_aborts_never_wedge():
    redis, sid = await _session(max_per_round=50)
    for attempt in range(5):
        await _deliver(redis, sid, qid=_QID + attempt)
        await session_store.restore_delivered(redis, sid, _SENSE, _QID + attempt)
    # Still deliverable after five aborted answers.
    assert await _deliver(redis, sid, qid=_QID + 99)


# --- the purged-question path (question_not_available) ----------------------


async def test_reopen_bound_delivery_finds_the_sense_without_a_sense_id():
    """A purged question carries no sense, so the binding is found by scanning.

    This is the ``question_not_available`` rejection: it is raised before
    ``consume_delivered``, so nothing had released the bind, and the question no
    longer exists for the client to resubmit. Without this the sense was stranded
    permanently — a strictly worse wedge than the aborted-answer one.
    """
    redis, sid = await _session(
        [AdmittedSense(_SENSE, "due", [2, 2]), AdmittedSense(_OTHER_SENSE, "due", [2, 2])]
    )
    await _deliver(redis, sid, _SENSE, _QID)

    reopened = await session_store.reopen_bound_delivery(redis, sid, _QID)

    assert reopened == _SENSE
    assert await session_store.get_delivered(redis, sid, _SENSE) is None
    assert await _deliver(redis, sid, _SENSE, _QID)


async def test_reopen_bound_delivery_only_touches_the_bound_sense():
    """A caller must not be able to reset an arbitrary sense's checkpoint."""
    redis, sid = await _session(
        [AdmittedSense(_SENSE, "due", [2, 2]), AdmittedSense(_OTHER_SENSE, "due", [2, 2])]
    )
    await _deliver(redis, sid, _SENSE, _QID)
    await _deliver(redis, sid, _OTHER_SENSE, _QID + 1)

    # An unrelated question id reopens nothing.
    assert await session_store.reopen_bound_delivery(redis, sid, 999999) is None
    assert await session_store.get_delivered(redis, sid, _SENSE) == _QID
    assert await session_store.get_delivered(redis, sid, _OTHER_SENSE) == _QID + 1

    # And reopening one leaves the other's bind intact.
    assert await session_store.reopen_bound_delivery(redis, sid, _QID) == _SENSE
    assert await session_store.get_delivered(redis, sid, _OTHER_SENSE) == _QID + 1


async def test_reopen_is_a_noop_once_the_session_is_gone():
    redis, sid = await _session()
    await _deliver(redis, sid)
    await session_store.end_session(redis, sid)

    # Must not resurrect keys for a session that no longer exists.
    await session_store.restore_delivered(redis, sid, _SENSE, _QID)

    assert await session_store.get_meta(redis, sid) is None
    assert await session_store.get_progress(redis, sid, _SENSE) is None
