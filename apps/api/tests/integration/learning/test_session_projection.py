"""The Redis projection schedules one ungraded re-ask and stays idempotent."""

from uuid import UUID, uuid4

import pytest

from pycil.learning import session_store

pytestmark = pytest.mark.asyncio


async def test_wrong_grade_adds_one_reask_and_duplicate_projection_is_noop(fake_redis):
    session_id = "projection-session"
    sense_id = 41
    await session_store.create(
        fake_redis,
        session_id,
        owner_id=uuid4(),
        node_id=uuid4(),
        scope_generation=1,
        target_words=1,
        max_per_round=2,
        admitted=[session_store.AdmittedSense(sense_id, "new", 1)],
    )

    assert await session_store.apply_grade_projection(
        fake_redis,
        session_id,
        sense_id,
        response_id=UUID(int=1),
        served_level=3,
        correct=False,
        failed_round=0,
    )
    progress = await session_store.get_progress(fake_redis, session_id, sense_id)
    assert progress is not None
    assert progress.reask_pending is True
    assert progress.reask_level == 3
    assert await session_store.apply_grade_projection(
        fake_redis,
        session_id,
        sense_id,
        response_id=UUID(int=2),
        served_level=3,
        correct=True,
        failed_round=0,
    )
    progress = await session_store.get_progress(fake_redis, session_id, sense_id)
    assert progress is not None and progress.reask_pending is True
    assert await session_store.complete_reask(fake_redis, session_id, sense_id)
    assert not await session_store.complete_reask(fake_redis, session_id, sense_id)
    progress = await session_store.get_progress(fake_redis, session_id, sense_id)
    assert progress is not None and progress.terminal is True
