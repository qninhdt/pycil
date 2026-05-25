"""Redis lock + spend counter helpers (shared between pycil-core and worker)."""
from __future__ import annotations

from datetime import datetime, timezone

from redis.asyncio import Redis

# Lua: SET key value NX EX ttl. Returns the value of the holder (the new one
# we just set, OR the existing one). This lets us cost-dedup: subsequent
# enqueues read the existing job_id from the lock holder.
_LOCK_LUA = """
local current = redis.call('GET', KEYS[1])
if current then return current end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return ARGV[1]
"""


async def acquire_or_get_lock(
    redis: Redis, key: str, value: str, ttl_seconds: int
) -> str:
    """Atomically: if key exists return its value; else SET and return value."""
    result = await redis.eval(_LOCK_LUA, 1, key, value, ttl_seconds)  # type: ignore[arg-type]
    if isinstance(result, bytes):
        return result.decode()
    return str(result)


SPEND_KEY_PREFIX = "openrouter:spend"


def _spend_key_today() -> str:
    """UTC-day partitioned spend counter; resets at 00:00Z naturally."""
    return f"{SPEND_KEY_PREFIX}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"


async def get_spend_daily(redis: Redis) -> float:
    raw = await redis.get(_spend_key_today())
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


async def add_spend(redis: Redis, usd: float) -> float:
    key = _spend_key_today()
    val = await redis.incrbyfloat(key, usd)
    # Two-day TTL: covers in-flight requests around midnight rollover.
    await redis.expire(key, 2 * 86_400)
    return float(val)
