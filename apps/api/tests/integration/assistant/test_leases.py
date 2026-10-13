import asyncio
from uuid import uuid4

import pytest
from anyio import sleep

from pycil.app.http import Problem
from pycil.assistant import conversations
from pycil.assistant.conversations import guard


async def test_lease_contention_and_exception_cleanup_use_real_redis(redis_store):
    redis, _ = redis_store
    identifier = uuid4()
    with pytest.raises(RuntimeError):
        async with guard(redis, identifier):
            with pytest.raises(Problem) as error:
                async with guard(redis, identifier):
                    pytest.fail("second holder acquired the lease")
            assert error.value.code == "conversation_busy"
            raise RuntimeError("work failed")
    async with guard(redis, identifier):
        assert await redis.exists(f"pycil:conversation:{identifier}") == 1
    assert await redis.exists(f"pycil:conversation:{identifier}") == 0


async def test_cancelled_lease_owner_joins_cleanup_before_reacquisition(redis_store):
    redis, _ = redis_store
    identifier, started = uuid4(), asyncio.Event()

    async def worker():
        async with guard(redis, identifier):
            started.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(worker())
    try:
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with guard(redis, identifier):
            assert await redis.exists(f"pycil:conversation:{identifier}") == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_old_holder_never_releases_replacement_holders_lease(redis_store):
    redis, _ = redis_store
    identifier = uuid4()
    key = f"pycil:conversation:{identifier}"
    try:
        with pytest.raises(Problem) as error:
            async with guard(redis, identifier):
                await redis.set(key, "replacement-owner", ex=30)
        assert error.value.code == "conversation_lock_lost"
        assert await redis.get(key) == b"replacement-owner"
    finally:
        await redis.delete(key)


async def test_lease_is_renewed_past_original_expiry(redis_store, monkeypatch):
    redis, _ = redis_store
    monkeypatch.setattr(conversations, "LOCK_TTL_SECONDS", 0.9)
    identifier = uuid4()
    key = f"pycil:conversation:{identifier}"
    async with asyncio.timeout(5), guard(redis, identifier):
        owner = await redis.get(key)
        # Wait past the actual initial Redis expiry, while native renewal runs.
        await sleep(1.2)
        assert await redis.get(key) == owner
        assert await redis.pttl(key) > 0
        with pytest.raises(Problem) as error:
            async with guard(redis, identifier):
                pytest.fail("renewed holder lost exclusivity")
        assert error.value.code == "conversation_busy"
    assert not await redis.exists(key)


async def test_renewal_loss_cancels_running_work_without_deleting_new_holder(
    redis_store, monkeypatch
):
    redis, _ = redis_store
    monkeypatch.setattr(conversations, "LOCK_TTL_SECONDS", 0.9)
    identifier, cleaned = uuid4(), asyncio.Event()
    key = f"pycil:conversation:{identifier}"
    try:
        with pytest.raises(Problem) as error:
            async with asyncio.timeout(5), guard(redis, identifier):
                await redis.set(key, "new-holder", ex=30)
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaned.set()
        assert error.value.code == "conversation_lock_lost"
        assert cleaned.is_set()
        assert await redis.get(key) == b"new-holder"
    finally:
        await redis.delete(key)
