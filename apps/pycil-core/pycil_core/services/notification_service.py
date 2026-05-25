"""Persisted notifications: insert + read + mark-read.

Replaces the v1 localStorage scheme. Worker emits via Redis pubsub
`notifications:user:{uid}`; FE polls `GET /notifications?since=` every 30s.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def create(
    session: AsyncSession,
    *,
    user_id: UUID,
    kind: str,
    payload: dict[str, Any] | None = None,
) -> UUID:
    """Insert a notification. `kind` is a snake_case discriminator."""
    import json as _json
    row = (
        await session.execute(
            text(
                """
                INSERT INTO notifications (user_id, kind, payload)
                VALUES (:uid, :kind, CAST(:payload AS jsonb))
                RETURNING id
                """
            ),
            {"uid": user_id, "kind": kind, "payload": _json.dumps(payload or {})},
        )
    ).one()
    await session.commit()
    return row.id


async def list_for_user(
    session: AsyncSession,
    *,
    user_id: UUID,
    since: datetime | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return user's recent notifications. `since` filters strictly after that ts."""
    rows = (
        await session.execute(
            text(
                """
                SELECT id, kind, payload, read_at, created_at
                  FROM notifications
                 WHERE user_id = :uid
                   AND (:since IS NULL OR created_at > :since)
                 ORDER BY created_at DESC
                 LIMIT :limit
                """
            ),
            {"uid": user_id, "since": since, "limit": limit},
        )
    ).all()
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
    result = await session.execute(
        text(
            """
            UPDATE notifications
               SET read_at = NOW()
             WHERE user_id = :uid
               AND id = ANY(CAST(:ids AS uuid[]))
               AND read_at IS NULL
            """
        ),
        {"uid": user_id, "ids": [str(i) for i in ids]},
    )
    await session.commit()
    return int(getattr(result, "rowcount", 0) or 0)


async def unread_count(
    session: AsyncSession, *, user_id: UUID
) -> int:
    row = (
        await session.execute(
            text(
                "SELECT COUNT(*) AS n FROM notifications "
                "WHERE user_id = :uid AND read_at IS NULL"
            ),
            {"uid": user_id},
        )
    ).one()
    return int(row.n)
