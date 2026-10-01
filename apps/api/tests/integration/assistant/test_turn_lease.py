"""Assistant execution slots are short lived and owner guarded."""

import asyncio
from uuid import uuid4

import pytest

from pycil.assistant.turns import leases as turn_lease
from pycil.billing.plans import PlanKey

pytestmark = pytest.mark.asyncio


async def test_turn_lease_renews_only_for_its_current_owner(fake_redis, monkeypatch):
    monkeypatch.setattr(turn_lease, "lease_ttl_seconds", lambda: 3)
    user_id = uuid4()
    thread_id = uuid4()
    lease = await turn_lease.acquire_turn_lease(fake_redis, user_id, thread_id, PlanKey.free)
    assert lease is not None

    await asyncio.sleep(1.1)
    assert await turn_lease.renew_turn_lease(fake_redis, lease)
    assert await fake_redis.pttl(turn_lease.thread_lease_key(thread_id)) > 1_000
    assert await turn_lease.acquire_turn_lease(fake_redis, user_id, uuid4(), PlanKey.free) is None
    assert await turn_lease.acquire_turn_lease(fake_redis, user_id, thread_id, PlanKey.pro) is None
    assert await turn_lease.release_turn_lease(fake_redis, lease)


async def test_pro_has_five_slots_and_pending_approval_uses_none(fake_redis):
    user_id = uuid4()
    leases = [
        await turn_lease.acquire_turn_lease(fake_redis, user_id, uuid4(), PlanKey.pro)
        for _ in range(5)
    ]
    assert all(leases)
    assert await turn_lease.acquire_turn_lease(fake_redis, user_id, uuid4(), PlanKey.pro) is None
    assert await turn_lease.acquire_turn_lease(fake_redis, user_id, uuid4(), PlanKey.free) is None
    for lease in leases:
        assert await turn_lease.release_turn_lease(fake_redis, lease)
    assert await turn_lease.acquire_turn_lease(fake_redis, user_id, uuid4(), PlanKey.free)


async def test_start_rate_limits_the_eleventh_attempt(fake_redis):
    user_id = uuid4()
    results = [await turn_lease.check_start_rate(fake_redis, user_id) for _ in range(10)]
    assert results == [None] * 10
    assert await turn_lease.check_start_rate(fake_redis, user_id) > 0


async def test_release_clears_its_slot_even_if_the_thread_key_was_replaced(fake_redis):
    user_id, thread_id = uuid4(), uuid4()
    lease = await turn_lease.acquire_turn_lease(fake_redis, user_id, thread_id, PlanKey.pro)
    assert lease is not None
    await fake_redis.set(turn_lease.thread_lease_key(thread_id), "new-owner")

    assert await turn_lease.release_turn_lease(fake_redis, lease)
    assert await fake_redis.get(turn_lease.thread_lease_key(thread_id)) == "new-owner"
    assert await turn_lease.acquire_turn_lease(fake_redis, user_id, uuid4(), PlanKey.pro)
