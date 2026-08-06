"""Centrifugo subscribe-proxy authorization for durable async snapshots."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.tasks.infra.models import AsyncTaskEvent, AsyncTaskInterest

_CHANNEL_PREFIX = "async:"
_DENIED = {"error": {"code": 103, "message": "permission denied"}}

# How the caller answers "what token_version does this user currently have?".
# Returns None when the user does not exist.
#
# Injected rather than imported so this module does not depend on `auth`. It read
# exactly one integer off the ORM `User`, while `auth.router` imports
# `realtime.client.disconnect_user` — one integer in one direction and one
# function in the other, which was the whole `auth <-> realtime` cycle. Passing
# the lookup in costs one parameter and removes the edge.
TokenVersionLookup = Callable[[AsyncSession, UUID], Awaitable[int | None]]


class SubscribeProxyRequest(BaseModel):
    """The minimal trusted fields Centrifugo sends to its subscribe proxy."""

    user: str
    channel: str
    meta: dict = Field(default_factory=dict)


def _resource_id(channel: str) -> UUID | None:
    if not channel.startswith(_CHANNEL_PREFIX):
        return None
    try:
        task_id = UUID(channel.removeprefix(_CHANNEL_PREFIX))
    except ValueError:
        return None
    return task_id if channel == f"{_CHANNEL_PREFIX}{task_id}" else None


async def authorize_subscription(
    session: AsyncSession,
    body: SubscribeProxyRequest,
    current_token_version: TokenVersionLookup,
) -> dict:
    """Fail closed unless a live interest and current auth version authorize it."""
    task_id = _resource_id(body.channel)
    try:
        user_id = UUID(body.user)
        token_version = int(body.meta["tokenVersion"])
        expires_at = int(body.meta["expiresAt"])
    except (KeyError, TypeError, ValueError):
        return _DENIED
    if task_id is None or expires_at <= int(datetime.now(UTC).timestamp()):
        return _DENIED

    current_version = await current_token_version(session, user_id)
    if current_version is None or current_version != token_version:
        return _DENIED

    now = datetime.now(UTC)
    # Both columns are read in one row, because `expires_at` is nullable: selecting
    # it alone makes "no live interest" and "a live interest with no deadline"
    # indistinguishable, and treating the second as the first denies valid readers.
    interest = (
        await session.execute(
            select(AsyncTaskInterest.id, AsyncTaskInterest.expires_at).where(
                AsyncTaskInterest.task_id == task_id,
                AsyncTaskInterest.requester_id == user_id,
                AsyncTaskInterest.revoked_at.is_(None),
                or_(AsyncTaskInterest.expires_at.is_(None), AsyncTaskInterest.expires_at > now),
            )
        )
    ).first()
    if interest is None:
        return _DENIED

    snapshot = await session.scalar(
        select(AsyncTaskEvent.snapshot)
        .where(AsyncTaskEvent.task_id == task_id)
        .order_by(AsyncTaskEvent.version.desc())
        .limit(1)
    )
    if snapshot is None:
        return _DENIED
    # Centrifugo enforces `expire_at` on its own clock, so returning the token's
    # value let a subscription authorized one second before its interest lapsed run
    # on for the token's remaining 900s. The connection token carries no revocation
    # list, which makes this clamp the only bound on an established subscription.
    if interest.expires_at is not None:
        expires_at = min(expires_at, int(interest.expires_at.timestamp()))
    # `data` is the same versioned DTO sent by the transactional outbox. Redis
    # history recovers the narrow read/activation race; this snapshot heals any
    # longer disconnect or history eviction.
    return {"result": {"data": snapshot, "expire_at": expires_at}}
