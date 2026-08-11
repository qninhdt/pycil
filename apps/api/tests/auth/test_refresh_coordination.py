"""Distributed refresh single-flight behavior."""

import asyncio
from typing import cast

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from pycil.auth import refresh_coordination
from pycil.auth.schemas import TokenResponse

pytestmark = pytest.mark.asyncio


def _tokens(access_token: str = "access") -> TokenResponse:
    return TokenResponse(
        access_token=access_token,
        refresh_token=f"refresh-{access_token}",
        expires_in=900,
        refresh_expires_in=86_400,
    )


async def test_overlapping_refreshes_serialize_and_converge(fake_redis):
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0
    active = 0
    max_active = 0

    async def operation() -> TokenResponse:
        nonlocal active, calls, max_active
        calls += 1
        active += 1
        max_active = max(max_active, active)
        started.set()
        await release.wait()
        active -= 1
        return _tokens()

    first = asyncio.create_task(
        refresh_coordination.coordinate_refresh(fake_redis, "raw", operation)
    )
    await started.wait()
    second = asyncio.create_task(
        refresh_coordination.coordinate_refresh(fake_redis, "raw", operation)
    )
    await asyncio.sleep(0)
    assert not second.done()

    release.set()
    assert await asyncio.gather(first, second) == [_tokens(), _tokens()]
    assert calls == 2
    assert max_active == 1
    _, outcome_key = refresh_coordination._keys("raw")
    stored = await fake_redis.get(outcome_key)
    assert stored.endswith(":ok")
    assert "access" not in stored
    assert "refresh-access" not in stored


async def test_overlapping_invalid_refreshes_share_the_invalid_result(fake_redis):
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def operation() -> None:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return None

    first = asyncio.create_task(
        refresh_coordination.coordinate_refresh(fake_redis, "raw", operation)
    )
    await started.wait()
    second = asyncio.create_task(
        refresh_coordination.coordinate_refresh(fake_redis, "raw", operation)
    )
    await asyncio.sleep(0)
    release.set()

    assert await asyncio.gather(first, second) == [None, None]
    assert calls == 1


async def test_sequential_reuse_still_runs_the_replay_operation(fake_redis):
    calls = 0

    async def operation() -> TokenResponse | None:
        nonlocal calls
        calls += 1
        return _tokens() if calls == 1 else None

    assert await refresh_coordination.coordinate_refresh(fake_redis, "raw", operation) == _tokens()
    assert await refresh_coordination.coordinate_refresh(fake_redis, "raw", operation) is None
    assert calls == 2


async def test_waiter_recovers_after_lock_expires_without_an_outcome(fake_redis, monkeypatch):
    monkeypatch.setattr(refresh_coordination, "_WAIT_TIMEOUT_SECONDS", 0.03)
    monkeypatch.setattr(refresh_coordination, "_POLL_INTERVAL_SECONDS", 0.001)
    lock_key, _ = refresh_coordination._keys("raw")
    await fake_redis.set(lock_key, "abandoned-leader", px=10)

    async def operation() -> TokenResponse:
        return _tokens("recovered")

    assert await refresh_coordination.coordinate_refresh(fake_redis, "raw", operation) == _tokens(
        "recovered"
    )


async def test_redis_failure_fails_closed(fake_redis):
    class BrokenRedis:
        async def set(self, *args, **kwargs):
            del args, kwargs
            raise RedisError("redis is down")

    async def operation() -> TokenResponse:
        raise AssertionError("the operation must not run without coordination")

    with pytest.raises(refresh_coordination.RefreshCoordinationError, match="unavailable"):
        await refresh_coordination.coordinate_refresh(cast(Redis, BrokenRedis()), "raw", operation)

    class BrokenStateRedis:
        async def set(self, *args, **kwargs):
            del args, kwargs
            return False

        async def eval(self, *args, **kwargs):
            del args, kwargs
            raise RedisError("redis state is down")

    with pytest.raises(refresh_coordination.RefreshCoordinationError, match="unavailable"):
        await refresh_coordination.coordinate_refresh(
            cast(Redis, BrokenStateRedis()), "raw", operation
        )

    class HangingStateRedis:
        async def set(self, *args, **kwargs):
            del args, kwargs
            return False

        async def eval(self, *args, **kwargs):
            del args, kwargs
            await asyncio.sleep(1)

    with pytest.raises(refresh_coordination.RefreshCoordinationError, match="unavailable"):
        await refresh_coordination.coordinate_refresh(
            cast(Redis, HangingStateRedis()), "raw", operation
        )


async def test_stale_outcome_does_not_satisfy_a_new_lock_generation(fake_redis, monkeypatch):
    monkeypatch.setattr(refresh_coordination, "_WAIT_TIMEOUT_SECONDS", 0.03)
    monkeypatch.setattr(refresh_coordination, "_POLL_INTERVAL_SECONDS", 0.001)
    lock_key, outcome_key = refresh_coordination._keys("raw")
    await fake_redis.set(outcome_key, "old-owner:ok", ex=1)
    await fake_redis.set(lock_key, "new-owner", px=10)

    async def operation() -> TokenResponse:
        return _tokens("new-generation")

    result = await refresh_coordination.coordinate_refresh(fake_redis, "raw", operation)
    assert result == _tokens("new-generation")


async def test_failed_leader_wakes_waiters_with_a_safe_retry(fake_redis):
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def operation() -> TokenResponse:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        if calls == 1:
            raise RuntimeError("database outcome unknown")
        return _tokens("recovered")

    first = asyncio.create_task(
        refresh_coordination.coordinate_refresh(fake_redis, "raw", operation)
    )
    await started.wait()
    second = asyncio.create_task(
        refresh_coordination.coordinate_refresh(fake_redis, "raw", operation)
    )
    await asyncio.sleep(0)
    release.set()

    first_result, second_result = await asyncio.gather(first, second, return_exceptions=True)
    assert isinstance(first_result, RuntimeError)
    assert second_result == _tokens("recovered")
    assert calls == 2


async def test_refresh_openapi_declares_coordination_errors():
    from pycil.main import create_app

    responses = create_app().openapi()["paths"]["/v1/auth/refresh"]["post"]["responses"]
    assert {"401", "422", "500", "503"}.issubset(responses)
    assert responses["422"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorEnvelope"
    )
