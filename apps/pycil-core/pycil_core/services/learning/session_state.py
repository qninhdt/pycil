"""Learning-session Redis state: keys, per-session lock, and JSON serde.

Lowest layer of the learning-session split (session_state → session_flow /
answer_grading). Owns the Redis key scheme, the SET-NX per-session lock that
serializes multi-tab races, and load/save of the session-state dict. No ELO or
question logic lives here.
"""

from __future__ import annotations

import json
import uuid as _uuid
from typing import Any

from fastapi import HTTPException, status
from redis.asyncio import Redis

from pycil_core.services.redis_pool import get_redis

_SESSION_TTL_SECONDS = 4 * 60 * 60
_LOCK_TTL_SECONDS = 30


def _redis() -> Redis:
    return get_redis()


def _session_key(session_id: str) -> str:
    return f"learning_session:{session_id}"


def _lock_key(session_id: str) -> str:
    return f"session_lock:{session_id}"


async def _acquire_lock(redis: Redis, session_id: str) -> str:
    """SET NX EX lock. Returns request_id; raises 409 on contention."""
    request_id = _uuid.uuid4().hex
    ok = await redis.set(_lock_key(session_id), request_id, nx=True, ex=_LOCK_TTL_SECONDS)
    if not ok:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "session_busy"},
        )
    return request_id


_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
else
  return 0
end
"""


async def _release_lock(redis: Redis, session_id: str, request_id: str) -> None:
    await redis.eval(_RELEASE_LUA, 1, _lock_key(session_id), request_id)


async def _load_state(redis: Redis, session_id: str) -> dict[str, Any]:
    raw = await redis.get(_session_key(session_id))
    if not raw:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session_not_found")
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "session_corrupt") from e


async def _save_state(redis: Redis, session_id: str, state: dict) -> None:
    await redis.set(
        _session_key(session_id),
        json.dumps(state, default=str),
        ex=_SESSION_TTL_SECONDS,
    )
