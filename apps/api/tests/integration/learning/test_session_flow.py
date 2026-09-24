"""Session delivery keeps re-asks ungraded."""

import random
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from pycil.learning import delivery, session_store
from pycil.learning import session as study_session
from tests.support.lexi_fakes import FakeLexiReader

pytestmark = pytest.mark.asyncio


async def test_reask_delivery_preserves_its_kind(fake_redis):
    session_id = "reask-delivery"
    sense_id = 42
    await session_store.create(
        fake_redis,
        session_id,
        owner_id=uuid4(),
        node_id=uuid4(),
        scope_generation=1,
        target_words=1,
        max_per_round=2,
        admitted=[session_store.AdmittedSense(sense_id, "due", 3)],
    )
    await session_store.apply_grade_projection(
        fake_redis,
        session_id,
        sense_id,
        response_id=uuid4(),
        served_level=3,
        correct=False,
        failed_round=0,
    )
    await session_store.advance_round(fake_redis, session_id, expected_round=0)

    reader = FakeLexiReader()
    reader.add_supply(sense_id, 3, "cloze")
    requirement = (await delivery.round_candidates(fake_redis, session_id, 1))[0]
    assert requirement.kind == "reask"

    outcome = await study_session._try_deliver(
        fake_redis,
        reader,
        session_id=session_id,
        requirement=requirement,
        round_index=1,
        rng=random.Random(0),
        unresolved=[],
    )

    assert outcome is not None
    current_delivery = await session_store.get_delivery(fake_redis, session_id, sense_id)
    assert current_delivery is not None and current_delivery.kind == "reask"


async def test_terminal_session_uses_the_session_completion_contract(fake_redis, monkeypatch):
    session_id = "terminal-session"
    owner_id = uuid4()
    await session_store.create(
        fake_redis,
        session_id,
        owner_id=owner_id,
        node_id=uuid4(),
        scope_generation=1,
        target_words=1,
        max_per_round=1,
        admitted=[session_store.AdmittedSense(42, "due", 1)],
    )
    await session_store.apply_grade_projection(
        fake_redis,
        session_id,
        42,
        response_id=uuid4(),
        served_level=1,
        correct=True,
        failed_round=0,
    )
    meta = await session_store.get_meta(fake_redis, session_id)
    assert meta is not None
    seen: list[tuple[object, str]] = []

    async def complete(redis, current_session_id):
        seen.append((redis, current_session_id))
        return True

    monkeypatch.setattr(delivery, "session_complete", complete)
    persist = AsyncMock()
    monkeypatch.setattr(study_session.recap, "persist", persist)

    outcome = await study_session.next_question(
        None,
        fake_redis,
        FakeLexiReader(),
        session_id=session_id,
        user=SimpleNamespace(id=owner_id),
        meta=meta,
    )

    assert outcome.reason == "exhausted"
    assert seen == [(fake_redis, session_id)]
    persist.assert_awaited_once()
