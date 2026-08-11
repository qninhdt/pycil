"""Distributed coordination for rotating refresh tokens.

PostgreSQL remains authoritative for token consumption and replay containment.
Redis serializes overlapping callers and publishes only an outcome marker. The
database's bounded replay grace recovers the successor after a process/Redis
failure, so bearer tokens never enter Redis.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Awaitable, Callable
from typing import cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from pycil.auth.refresh_sessions import token_digest
from pycil.auth.schemas import TokenResponse
from pycil.config import (
    REFRESH_COORDINATION_LOCK_TTL_SECONDS,
    REFRESH_COORDINATION_WAIT_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

# The Redis lease is an optimization, not the correctness boundary. If it expires,
# the database replay grace recovers a committed successor or performs the first
# rotation when the leader died before committing.
_LOCK_TTL_SECONDS = REFRESH_COORDINATION_LOCK_TTL_SECONDS
_OUTCOME_TTL_SECONDS = 60
_WAIT_TIMEOUT_SECONDS = REFRESH_COORDINATION_WAIT_TIMEOUT_SECONDS
_POLL_INTERVAL_SECONDS = 0.01
_REDIS_OPERATION_TIMEOUT_SECONDS = 1.0

_RELEASE_LOCK = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""

_READ_STATE = """
return {
    redis.call('GET', KEYS[1]) or '',
    redis.call('GET', KEYS[2]) or ''
}
"""


class RefreshCoordinationError(RuntimeError):
    """A refresh cannot safely proceed because its Redis coordination is unknown."""


RefreshOperation = Callable[[], Awaitable[TokenResponse | None]]


def _keys(raw_token: str) -> tuple[str, str]:
    # The peppered digest is safe for a Redis key; the raw bearer credential never
    # appears in Redis, logs, or exception messages.
    digest = token_digest(raw_token)
    return f"auth:refresh:lock:{digest}", f"auth:refresh:result:{digest}"


def _encode_outcome(owner: str, result: TokenResponse | None) -> str:
    status = "ok" if result is not None else "invalid"
    return f"{owner}:{status}"


def _decode_outcome(raw: str | None, owner: str) -> str | None:
    if raw is None:
        return None
    marker_owner, separator, status = raw.partition(":")
    if not separator or marker_owner != owner:
        return None
    if status in {"ok", "invalid"}:
        return status
    raise RefreshCoordinationError("invalid refresh coordination result")


def _text(value: object) -> str | None:
    if value in (None, "", b""):
        return None
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, str):
        return value
    raise RefreshCoordinationError("invalid refresh coordination state")


async def _read_state(
    redis: Redis, lock_key: str, outcome_key: str
) -> tuple[str | None, str | None]:
    try:
        state = await asyncio.wait_for(
            cast(
                Awaitable[object],
                redis.eval(_READ_STATE, 2, lock_key, outcome_key),  # pyright: ignore[reportGeneralTypeIssues]
            ),
            timeout=_REDIS_OPERATION_TIMEOUT_SECONDS,
        )
    except (RedisError, TimeoutError) as exc:
        raise RefreshCoordinationError("refresh coordination unavailable") from exc
    if not isinstance(state, list | tuple) or len(state) != 2:
        raise RefreshCoordinationError("invalid refresh coordination state")
    return _text(state[0]), _text(state[1])


async def _release(redis: Redis, key: str, owner: str) -> None:
    try:
        await asyncio.wait_for(
            cast(
                Awaitable[object],
                redis.eval(_RELEASE_LOCK, 1, key, owner),  # pyright: ignore[reportGeneralTypeIssues]
            ),
            timeout=_REDIS_OPERATION_TIMEOUT_SECONDS,
        )
    except (RedisError, TimeoutError):
        # The lease is bounded and the result is already published. A release
        # failure is safe to recover from, though it may delay the next attempt.
        logger.warning("could not release refresh coordination lock", exc_info=True)


async def _wait_for_leader(
    redis: Redis,
    lock_key: str,
    outcome_key: str,
    owner: str,
    operation: RefreshOperation,
) -> TokenResponse | None:
    deadline = asyncio.get_running_loop().time() + _WAIT_TIMEOUT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        active_owner, raw_outcome = await _read_state(redis, lock_key, outcome_key)
        if active_owner is not None and active_owner != owner:
            # A lease changed hands. Follow the new generation; never accept an
            # outcome marker belonging to the old owner.
            owner = active_owner

        outcome = _decode_outcome(raw_outcome, owner)
        if outcome == "invalid":
            return None
        if outcome == "error":
            raise RefreshCoordinationError("refresh operation failed")
        if active_owner is None:
            # The leader has released. A success marker means the durable replay
            # path can recover the same successor; no marker means the leader may
            # have crashed before publishing, which is also recoverable there.
            return await operation()
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    raise RefreshCoordinationError("refresh coordination timed out")


async def coordinate_refresh(
    redis: Redis, raw_token: str, operation: RefreshOperation
) -> TokenResponse | None:
    """Serialize overlapping refresh operations and converge on one successor.

    A caller that wins the lock always executes the operation. The outcome key is
    intentionally not checked before lock acquisition: a later sequential reuse
    must still reach PostgreSQL and trigger the existing replay policy.
    """
    lock_key, outcome_key = _keys(raw_token)
    owner = secrets.token_urlsafe(18)
    try:
        acquired = await asyncio.wait_for(
            redis.set(lock_key, owner, nx=True, ex=_LOCK_TTL_SECONDS),
            timeout=_REDIS_OPERATION_TIMEOUT_SECONDS,
        )
    except (RedisError, TimeoutError) as exc:
        raise RefreshCoordinationError("refresh coordination unavailable") from exc

    if not acquired:
        active_owner, _ = await _read_state(redis, lock_key, outcome_key)
        if active_owner is None:
            return await operation()
        return await _wait_for_leader(redis, lock_key, outcome_key, active_owner, operation)

    try:
        result = await operation()

        try:
            await asyncio.wait_for(
                redis.set(
                    outcome_key,
                    _encode_outcome(owner, result),
                    ex=_OUTCOME_TTL_SECONDS,
                ),
                timeout=_REDIS_OPERATION_TIMEOUT_SECONDS,
            )
        except (RedisError, TimeoutError):
            logger.warning("could not publish refresh coordination result", exc_info=True)
        return result
    finally:
        await _release(redis, lock_key, owner)
