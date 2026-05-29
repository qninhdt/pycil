"""Persisted notifications: insert + read + mark-read.

Replaces the v1 localStorage scheme. Worker emits via Redis pubsub
`notifications:user:{uid}`; FE polls `GET /notifications?since=` every 30s.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from shared.db import Notification
from sqlalchemy import func, update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


async def create(
    session: AsyncSession,
    *,
    user_id: UUID,
    kind: str,
    payload: dict[str, Any] | None = None,
) -> UUID:
    """Insert a notification. `kind` is a snake_case discriminator."""
    record = Notification(user_id=user_id, kind=kind, payload=payload or {})
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record.id


async def list_for_user(
    session: AsyncSession,
    *,
    user_id: UUID,
    since: datetime | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return user's recent notifications. `since` filters strictly after that ts."""
    stmt = (
        select(
            Notification.id,
            Notification.kind,
            Notification.payload,
            Notification.read_at,
            Notification.created_at,
        )
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if since is not None:
        stmt = stmt.where(Notification.created_at > since)
    rows = (await session.exec(stmt)).all()
    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "payload": r.payload,
            "read_at": r.read_at.isoformat() if r.read_at else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


async def mark_read(
    session: AsyncSession, *, user_id: UUID, ids: list[UUID]
) -> int:
    """Mark notifications read. Caller-scoped via user_id. Returns count.

    Caps the input list at 500 ids to prevent expensive ANY-array scans
    if a client posts an unbounded selection.
    """
    if not ids:
        return 0
    if len(ids) > 500:
        ids = ids[:500]
    result = await session.exec(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.id.in_(ids),
            Notification.read_at.is_(None),
        )
        .values(read_at=func.now())
    )
    await session.commit()
    return int(getattr(result, "rowcount", 0) or 0)


async def unread_count(
    session: AsyncSession, *, user_id: UUID
) -> int:
    return int(
        (
            await session.exec(
                select(func.count())
                .select_from(Notification)
                .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            )
        ).one()
    )
