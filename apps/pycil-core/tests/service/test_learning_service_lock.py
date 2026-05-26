"""Lock semantics on `learning_service` per-session SET NX EX lock.

Pinned invariants:
- First `_acquire_lock` call wins (truthy SET NX EX).
- Concurrent `_acquire_lock` raises 409 `session_busy`.
- `_release_lock` Lua compares request_id; foreign release is a no-op.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from pycil_core.services import learning_service as ls


SESSION_ID = "11111111-2222-3333-4444-555555555555"


async def test_first_acquire_wins(fakeredis_client) -> None:
    rid = await ls._acquire_lock(fakeredis_client, SESSION_ID)
    assert rid
    # Lock key contains the request id.
    stored = await fakeredis_client.get(ls._lock_key(SESSION_ID))
    assert stored == rid


async def test_second_acquire_raises_409(fakeredis_client) -> None:
    await ls._acquire_lock(fakeredis_client, SESSION_ID)

    with pytest.raises(HTTPException) as exc:
        await ls._acquire_lock(fakeredis_client, SESSION_ID)

    assert exc.value.status_code == 409
    assert exc.value.detail == {"code": "session_busy"}


async def test_release_lock_only_owner(fakeredis_client) -> None:
    rid_a = await ls._acquire_lock(fakeredis_client, SESSION_ID)

    # Foreign release: another request_id must NOT delete the key.
    await ls._release_lock(fakeredis_client, SESSION_ID, "not-the-owner")
    assert await fakeredis_client.get(ls._lock_key(SESSION_ID)) == rid_a

    # Owner release deletes.
    await ls._release_lock(fakeredis_client, SESSION_ID, rid_a)
    assert await fakeredis_client.get(ls._lock_key(SESSION_ID)) is None


async def test_release_lock_after_ttl_expiry_is_safe(fakeredis_client) -> None:
    """If the key TTL elapsed and the second caller now owns it, the original
    owner's release must NOT delete the new owner's key."""
    rid_a = await ls._acquire_lock(fakeredis_client, SESSION_ID)
    # Simulate expiry by manually overwriting.
    await fakeredis_client.delete(ls._lock_key(SESSION_ID))
    rid_b = await ls._acquire_lock(fakeredis_client, SESSION_ID)
    assert rid_b != rid_a

    await ls._release_lock(fakeredis_client, SESSION_ID, rid_a)
    # rid_b's lock untouched.
    assert await fakeredis_client.get(ls._lock_key(SESSION_ID)) == rid_b
