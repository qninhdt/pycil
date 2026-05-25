"""Redis lock + spend counter helpers (shared between pycil-core and worker)."""
from __future__ import annotations

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


SPEND_KEY_DAILY = "openrouter:spend:daily"


async def get_spend_daily(redis: Redis) -> float:
    raw = await redis.get(SPEND_KEY_DAILY)
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


async def add_spend(redis: Redis, usd: float) -> float:
    val = await redis.incrbyfloat(SPEND_KEY_DAILY, usd)
    # Daily key expires at end of day-ish (24h sliding is fine for v1).
    await redis.expire(SPEND_KEY_DAILY, 90_000)
    return float(val)
