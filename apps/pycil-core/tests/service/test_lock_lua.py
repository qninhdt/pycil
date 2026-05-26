"""LOCK_LUA primitive — GET-or-SET-with-EX, atomic.

Pinned (Validation Session 1, plan §V1):
- First call stores the caller's value, returns it (is_owner=True).
- Second call reads existing holder value, returns it (is_owner=False).
- After TTL expiry, first call again becomes owner.
"""
from __future__ import annotations

import asyncio

from pycil_core.services._job_enqueue import acquire_lock_or_get_owner


KEY = "lock:test:lua"


async def test_first_caller_owns(fakeredis_client) -> None:
    new, owner, is_owner = await acquire_lock_or_get_owner(
        fakeredis_client, lock_key=KEY, ttl_seconds=600
    )
    assert is_owner is True
    assert owner == new


async def test_second_caller_reads_existing_holder(fakeredis_client) -> None:
    a_new, _, _ = await acquire_lock_or_get_owner(
        fakeredis_client, lock_key=KEY, ttl_seconds=600
    )
    b_new, b_owner, b_is_owner = await acquire_lock_or_get_owner(
        fakeredis_client, lock_key=KEY, ttl_seconds=600
    )

    # b's "new id" is generated, but the lock returns a's value as the holder.
    assert b_is_owner is False
    assert b_owner == a_new
    assert b_new != a_new


async def test_lock_ttl_expiry_reclaims_ownership(fakeredis_client) -> None:
    """Short-TTL: after expiry the next caller becomes the new owner."""
    a_new, _, _ = await acquire_lock_or_get_owner(
        fakeredis_client, lock_key=KEY, ttl_seconds=1
    )
    # Wait past TTL.
    await asyncio.sleep(1.05)

    b_new, b_owner, b_is_owner = await acquire_lock_or_get_owner(
        fakeredis_client, lock_key=KEY, ttl_seconds=600
    )
    assert b_is_owner is True
    assert b_owner == b_new
    assert b_new != a_new


async def test_lock_holds_ttl(fakeredis_client) -> None:
    """Within TTL, repeated calls keep returning the original holder."""
    a_new, _, _ = await acquire_lock_or_get_owner(
        fakeredis_client, lock_key=KEY, ttl_seconds=600
    )
    for _ in range(3):
        _, owner, is_owner = await acquire_lock_or_get_owner(
            fakeredis_client, lock_key=KEY, ttl_seconds=600
        )
        assert is_owner is False
        assert owner == a_new
