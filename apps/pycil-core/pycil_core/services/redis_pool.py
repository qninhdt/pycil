"""Process-wide Redis connection pool.

One ConnectionPool per FastAPI worker (uvicorn forks before this module
loads). Replaces per-call `Redis.from_url(...)` patterns that exhausted
file descriptors and Redis maxclients under load.

Callers should use `get_redis()` and NOT `await redis.aclose()` — the pool
is shared. Lifespan tears down via `close_redis_pool()`.
"""
from __future__ import annotations

from redis.asyncio import ConnectionPool, Redis

from pycil_core.config import get_settings

_pool: ConnectionPool | None = None


def get_redis() -> Redis:
    """Return a Redis client backed by the shared connection pool."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            get_settings().redis_url,
            decode_responses=True,
            max_connections=20,
        )
    return Redis(connection_pool=_pool)


async def close_redis_pool() -> None:
    """Disconnect the pool. Called from lifespan finalizer."""
    global _pool
    if _pool is not None:
        await _pool.disconnect()
        _pool = None
