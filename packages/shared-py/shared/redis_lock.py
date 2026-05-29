"""Redis lock + spend counter helpers (shared between pycil-core and worker).

The Lua lock script is atomic GET-or-SET-with-TTL: it returns the current
holder if the key exists, otherwise sets the new value and returns it.
This lets callers cost-dedup: subsequent enqueues read the existing job_id
from the lock holder rather than starting a duplicate job.
"""
from __future__ import annotations

from datetime import UTC, datetime

from redis.asyncio import Redis

LOCK_LUA = """
local current = redis.call('GET', KEYS[1])
if current then return current end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return ARGV[1]
"""

SPEND_KEY_PREFIX = "openrouter:spend"
SPEND_TTL_SECONDS = 2 * 86_400


async def acquire_or_get_lock(
    redis: Redis, key: str, value: str, ttl_seconds: int
) -> str:
    """Atomically: if key exists return its value; else SET and return value."""
    result = await redis.eval(LOCK_LUA, 1, key, value, ttl_seconds)  # type: ignore[arg-type]
    if isinstance(result, bytes):
        return result.decode()
    return str(result)


def spend_key_today() -> str:
    """UTC-day partitioned spend counter; resets at 00:00Z naturally."""
    return f"{SPEND_KEY_PREFIX}:{datetime.now(UTC).strftime('%Y-%m-%d')}"


async def get_spend_daily(redis: Redis) -> float:
    raw = await redis.get(spend_key_today())
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


async def add_spend(redis: Redis, usd: float) -> float:
    key = spend_key_today()
    val = await redis.incrbyfloat(key, usd)
    # Two-day TTL covers in-flight requests around midnight rollover.
    await redis.expire(key, SPEND_TTL_SECONDS)
    return float(val)
