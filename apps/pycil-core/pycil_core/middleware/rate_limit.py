"""Redis sliding-window rate limit middleware for public routes.

Tracks per-IP request count over a 60s window in a Redis ZSET. Returns
429 when limit exceeded. Mounted on /public/* routes per phase 9 plan.

Caddy adds `X-Real-IP {remote_host}` (Caddyfile:20,24); read it directly
rather than hop-by-hop ProxyHeaders middleware. Falls back to
`request.client.host` when the header is absent (dev without proxy).
"""
from __future__ import annotations

import time
from uuid import uuid4

from fastapi import HTTPException, status
from starlette.requests import Request

from pycil_core.services.redis_pool import get_redis

_WINDOW_SECONDS = 60
_LIMIT_PER_IP = 60


def client_ip(request: Request) -> str:
    """Real client IP. Trusts `X-Real-IP` set by Caddy on the trusted-network
    boundary. Outside docker (no proxy), falls back to socket peer address."""
    header = request.headers.get("x-real-ip")
    if header:
        return header.strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


async def enforce(request_ip: str, route: str) -> None:
    """Raise 429 if `request_ip` has made >60 requests to /public/* in last 60s."""
    redis = get_redis()
    key = f"rl:{route}:{request_ip}"
    now_ms = int(time.time() * 1000)
    cutoff = now_ms - _WINDOW_SECONDS * 1000
    member = f"{now_ms}-{uuid4().hex}"

    async with redis.pipeline(transaction=True) as pipe:
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zadd(key, {member: now_ms})
        pipe.zcard(key)
        pipe.expire(key, _WINDOW_SECONDS * 2)
        _, _, count, _ = await pipe.execute()

    if int(count) > _LIMIT_PER_IP:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limit_exceeded",
            headers={"Retry-After": str(_WINDOW_SECONDS)},
        )
