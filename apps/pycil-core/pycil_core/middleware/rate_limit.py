"""Redis sliding-window rate limit middleware for public routes.

Tracks per-IP request count over a 60s window in a Redis ZSET. Returns
429 when limit exceeded. Mounted on /public/* routes per phase 9 plan.
"""
from __future__ import annotations

import time

from fastapi import HTTPException, status
from redis.asyncio import Redis

from pycil_core.config import get_settings


_WINDOW_SECONDS = 60
_LIMIT_PER_IP = 60


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


async def enforce(request_ip: str, route: str) -> None:
    """Raise 429 if `request_ip` has made >60 requests to /public/* in last 60s."""
    redis = _redis()
    key = f"rl:{route}:{request_ip}"
    now_ms = int(time.time() * 1000)
    cutoff = now_ms - _WINDOW_SECONDS * 1000

    try:
        # Drop expired entries; add current; count.
        async with redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zadd(key, {f"{now_ms}-{request_ip}": now_ms})
            pipe.zcard(key)
            pipe.expire(key, _WINDOW_SECONDS * 2)
            _, _, count, _ = await pipe.execute()
    finally:
        await redis.aclose()

    if int(count) > _LIMIT_PER_IP:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limit_exceeded",
            headers={"Retry-After": str(_WINDOW_SECONDS)},
        )
