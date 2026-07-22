"""Centrifugo subscribe-proxy authorization for durable async snapshots."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.models import User
from pycil.tasks.models import AsyncTaskEvent, AsyncTaskInterest

_CHANNEL_PREFIX = "async:"
_DENIED = {"error": {"code": 103, "message": "permission denied"}}


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


async def authorize_subscription(session: AsyncSession, body: SubscribeProxyRequest) -> dict:
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

    user = await session.get(User, user_id)
    if user is None or user.token_version != token_version:
        return _DENIED

    now = datetime.now(UTC)
    interest = await session.scalar(
        select(AsyncTaskInterest.id).where(
            AsyncTaskInterest.task_id == task_id,
            AsyncTaskInterest.requester_id == user_id,
            AsyncTaskInterest.revoked_at.is_(None),
            or_(AsyncTaskInterest.expires_at.is_(None), AsyncTaskInterest.expires_at > now),
        )
    )
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
    # `data` is the same versioned DTO sent by the transactional outbox. Redis
    # history recovers the narrow read/activation race; this snapshot heals any
    # longer disconnect or history eviction.
    return {"result": {"data": snapshot, "expire_at": expires_at}}
