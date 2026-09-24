"""Async Redis client for cache and coordination state."""

from uuid import uuid4

from redis.asyncio import Redis

from pycil.config import settings

_redis: Redis | None = None

#: Release only when the caller still holds the token. A plain DELETE would let a
#: request that already lost its lease delete the new holder's lock, which is the
#: classic way a mutual-exclusion primitive silently stops excluding.
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], tonumber(ARGV[2]))
end
return 0
"""


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def acquire_lease(redis: Redis, key: str, ttl_seconds: int) -> str | None:
    """Take a lease, or return ``None`` if another holder has it.

    ``SET NX PX`` is atomic, so two simultaneous requests cannot both win. The
    token is returned rather than stored because the holder is the only party
    that may release it.
    """
    token = uuid4().hex
    acquired = await redis.set(key, token, nx=True, px=max(1, ttl_seconds) * 1000)
    return token if acquired else None


async def release_lease(redis: Redis, key: str, token: str) -> bool:
    """Release a lease only if ``token`` still owns it."""
    released = await redis.eval(_RELEASE_SCRIPT, 1, key, token)
    return bool(released)


async def renew_lease(redis: Redis, key: str, token: str, ttl_seconds: int) -> bool:
    """Extend a lease only if ``token`` still owns it."""
    renewed = await redis.eval(
        _RENEW_SCRIPT, 1, key, token, max(1, ttl_seconds) * 1000
    )
    return bool(renewed)
