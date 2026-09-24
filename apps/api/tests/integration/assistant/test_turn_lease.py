"""Assistant turn lease remains owned while a stream is renewed."""

import asyncio
from uuid import uuid4

import pytest

from pycil.assistant.application import turn_lease

pytestmark = pytest.mark.asyncio


async def test_turn_lease_renews_only_for_its_current_owner(fake_redis, monkeypatch):
    monkeypatch.setattr(turn_lease, "lease_ttl_seconds", lambda: 2)
    user_id = uuid4()
    token = await turn_lease.acquire_turn_lease(fake_redis, user_id)
    assert token is not None

    await asyncio.sleep(1.1)
    assert await turn_lease.renew_turn_lease(fake_redis, user_id, token)
    assert await fake_redis.pttl(turn_lease.turn_lease_key(user_id)) > 1_000
    assert await turn_lease.renew_turn_lease(fake_redis, user_id, "other-owner") is False
    assert await turn_lease.acquire_turn_lease(fake_redis, user_id) is None
    assert await turn_lease.release_turn_lease(fake_redis, user_id, token)
