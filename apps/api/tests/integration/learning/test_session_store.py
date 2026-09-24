"""Unit and integration tests for Redis Single Document session store."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from pycil.common.errors import ConflictError
from pycil.learning import session_store


@pytest.mark.asyncio
async def test_session_store_single_doc_lifecycle(fake_redis):
    session_id = "test-single-doc-123"
    owner_id = uuid4()
    node_id = uuid4()
    sense_id = 999

    # 1. Create session
    meta = await session_store.create(
        fake_redis,
        session_id,
        owner_id=owner_id,
        node_id=node_id,
        scope_generation=1,
        target_words=5,
        max_per_round=3,
        admitted=[session_store.AdmittedSense(sense_id, "new", 2)],
    )
    assert meta.owner_id == owner_id
    assert meta.target_words == 5
    assert meta.new_count == 1

    # Verify only ONE key exists for session in Redis
    keys = await fake_redis.keys(f"pycil:session:{session_id}*")
    assert len(keys) == 1
    assert keys[0] == f"pycil:session:{session_id}"

    # 2. Get meta & progress
    read_meta = await session_store.get_meta(fake_redis, session_id)
    assert read_meta is not None
    assert read_meta.target_words == 5

    progress = await session_store.get_progress(fake_redis, session_id, sense_id)
    assert progress is not None
    assert progress.requested_level == 2
    assert progress.exposed is False

    # 3. Reserve delivery
    reserved = await session_store.reserve_round_delivery(
        fake_redis,
        session_id,
        sense_id,
        round_index=0,
        question_id=12345,
        kind="exposure",
    )
    assert reserved is True

    progress = await session_store.get_progress(fake_redis, session_id, sense_id)
    assert progress.exposed is True
    assert progress.current_qid == 12345
    assert progress.current_kind == "exposure"

    # 4. Consume delivered
    consumed = await session_store.consume_delivered(fake_redis, session_id, sense_id, 12345)
    assert consumed is True

    progress = await session_store.get_progress(fake_redis, session_id, sense_id)
    assert progress.current_qid is None

    # 5. Apply grade projection
    graded = await session_store.apply_grade_projection(
        fake_redis,
        session_id,
        sense_id,
        response_id=uuid4(),
        served_level=2,
        correct=True,
        failed_round=0,
    )
    assert graded is True
    assert await session_store.is_graded(fake_redis, session_id, sense_id) is True

    progress = await session_store.get_progress(fake_redis, session_id, sense_id)
    assert progress.terminal is True
    assert progress.terminal_reason == "completed"

    # 6. End session & verify total key cleanup
    await session_store.end_session(fake_redis, session_id)
    keys_after = await fake_redis.keys(f"pycil:session:{session_id}*")
    assert len(keys_after) == 0


@pytest.mark.asyncio
async def test_delivery_claim_expires_without_consuming_the_issued_question(fake_redis):
    session_id = "claim-lease"
    sense_id = 123
    await session_store.create(
        fake_redis,
        session_id,
        owner_id=uuid4(),
        node_id=uuid4(),
        scope_generation=1,
        target_words=1,
        max_per_round=1,
        admitted=[session_store.AdmittedSense(sense_id, "due", 1)],
    )
    await session_store.set_delivered(
        fake_redis, session_id, sense_id, 456, kind="grade", round_index=0
    )
    now = datetime.now(UTC)

    first = await session_store.claim_delivery(
        fake_redis, session_id, sense_id, 456, now=now
    )
    assert first
    assert await session_store.claim_delivery(
        fake_redis,
        session_id,
        sense_id,
        456,
        now=now + timedelta(seconds=29),
    ) is None

    retry = await session_store.claim_delivery(
        fake_redis,
        session_id,
        sense_id,
        456,
        now=now + timedelta(seconds=31),
    )
    assert retry and retry != first
    delivery = await session_store.get_delivery(fake_redis, session_id, sense_id)
    assert delivery is not None and delivery.question_id == 456


@pytest.mark.asyncio
async def test_concurrent_delivery_transitions_report_the_lost_compare(fake_redis, monkeypatch):
    session_id = "compare-version"
    sense_id = 321
    await session_store.create(
        fake_redis,
        session_id,
        owner_id=uuid4(),
        node_id=uuid4(),
        scope_generation=1,
        target_words=1,
        max_per_round=1,
        admitted=[session_store.AdmittedSense(sense_id, "due", 1)],
    )
    original_eval = fake_redis.eval
    both_read_same_version = asyncio.Event()
    arrivals = 0

    async def synchronized_eval(*args, **kwargs):
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            both_read_same_version.set()
        await both_read_same_version.wait()
        return await original_eval(*args, **kwargs)

    monkeypatch.setattr(fake_redis, "eval", synchronized_eval)
    results = await asyncio.gather(
        session_store.reserve_round_delivery(
            fake_redis, session_id, sense_id, 0, question_id=654
        ),
        session_store.reserve_round_delivery(
            fake_redis, session_id, sense_id, 0, question_id=987
        ),
        return_exceptions=True,
    )

    assert results.count(True) == 1
    conflicts = [result for result in results if isinstance(result, ConflictError)]
    assert len(conflicts) == 1
    assert conflicts[0].code == "study_session_changed"
    delivery = await session_store.get_delivery(fake_redis, session_id, sense_id)
    assert delivery is not None and delivery.question_id in {654, 987}


@pytest.mark.asyncio
async def test_mutation_keeps_the_original_session_expiry(fake_redis, monkeypatch):
    monkeypatch.setattr(session_store, "_ttl_seconds", lambda: 5)
    session_id = "fixed-expiry"
    sense_id = 456
    await session_store.create(
        fake_redis,
        session_id,
        owner_id=uuid4(),
        node_id=uuid4(),
        scope_generation=1,
        target_words=1,
        max_per_round=1,
        admitted=[session_store.AdmittedSense(sense_id, "due", 1)],
    )
    await asyncio.sleep(1.1)
    await session_store.set_delivered(
        fake_redis, session_id, sense_id, 789, kind="grade", round_index=0
    )

    ttl = await fake_redis.ttl(f"pycil:session:{session_id}")
    assert 0 < ttl < 5
