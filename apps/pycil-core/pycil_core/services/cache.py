"""Redis-backed cache helpers + Postgres advisory-lock guard for cron.

`get_or_set_json` wraps a fetch coroutine with a Redis read-through cache
keyed on a string. `invalidate_pattern` issues SCAN-based deletes for
namespace invalidation (e.g. on user mutation).

`advisory_lock` provides a contextmanager that acquires
`pg_advisory_xact_lock(hash(name))` for the duration of a transaction so
duplicate cron firings (multi-replica scale-out) are no-ops. Lock-winner
semantics: only one process executes the body per fire window.
"""
from __future__ import annotations

import json
import zlib
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

T = TypeVar("T")


async def get_or_set_json(
    redis: Redis,
    *,
    key: str,
    ttl: int,
    fetch: Callable[[], Awaitable[T | None]],
) -> T | None:
    """Read-through JSON cache. Returns None on cache miss + fetch returning None."""
    cached = await redis.get(key)
    if cached is not None:
        try:
            return json.loads(cached)
        except (TypeError, json.JSONDecodeError):
            await redis.delete(key)

    value = await fetch()
    if value is not None:
        await redis.set(key, json.dumps(value, default=str), ex=ttl)
    return value


async def invalidate_pattern(redis: Redis, *, pattern: str) -> int:
    """SCAN+DEL all keys matching pattern. Returns count deleted."""
    deleted = 0
    async for key in redis.scan_iter(match=pattern, count=200):
        deleted += await redis.delete(key)
    return deleted


def _name_to_lock_id(name: str) -> int:
    """Map a stable cron name to a 64-bit signed bigint for pg_advisory_lock."""
    digest = zlib.crc32(name.encode("utf-8")) & 0xFFFFFFFF
    if digest > 0x7FFFFFFF:
        digest -= 0x100000000
    return digest


@asynccontextmanager
async def advisory_lock(conn: AsyncConnection, name: str):
    """Yield True if the lock was acquired for this transaction; False otherwise.

    Usage:
        async with advisory_lock(conn, 'compute_league_rank') as acquired:
            if acquired:
                await do_work()

    Lock is held for the duration of the surrounding transaction. Concurrent
    invocations on other replicas see acquired=False and skip the body.
    """
    lock_id = _name_to_lock_id(name)
    result = await conn.execute(
        text("SELECT pg_try_advisory_xact_lock(:lock_id) AS got"),
        {"lock_id": lock_id},
    )
    row = result.first()
    acquired = bool(row and row.got)
    yield acquired
