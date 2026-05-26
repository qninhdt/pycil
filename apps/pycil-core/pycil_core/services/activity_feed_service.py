"""Activity feed (P5 phase 5 + P9 phase 3).

Append-only event log surfaced in the user's home screen and follower
inbox. Minimal helpers — list current user's events, list events from
followees, append a new event from any service that wants to emit.
"""
from __future__ import annotations

import json
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def append(
    session: AsyncSession,
    user_id: UUID,
    kind: str,
    payload: dict[str, Any] | None = None,
) -> int:
    row = (
        await session.execute(
            text(
                "INSERT INTO activity_events (user_id, kind, payload) "
                "VALUES (:u, :k, CAST(:p AS jsonb)) RETURNING id"
            ),
            {"u": user_id, "k": kind, "p": json.dumps(payload or {}, default=str)},
        )
    ).one()
    return int(row.id)


async def list_for_user(
    session: AsyncSession, user_id: UUID, limit: int = 50
) -> Sequence[dict]:
    rows = (
        await session.execute(
            text(
                "SELECT id, kind, payload, created_at FROM activity_events "
                "WHERE user_id = :u ORDER BY created_at DESC LIMIT :n"
            ),
            {"u": user_id, "n": limit},
        )
    ).all()
    return [
        {
            "id": int(r.id),
            "kind": r.kind,
            "payload": dict(r.payload or {}),
            "created_at": r.created_at,
        }
        for r in rows
    ]


async def list_for_followees(
    session: AsyncSession, user_id: UUID, limit: int = 50
) -> Sequence[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT a.id, a.user_id, a.kind, a.payload, a.created_at
                  FROM activity_events a
                  JOIN follows f
                    ON f.followee_id = a.user_id
                   AND f.follower_id = :uid
                 ORDER BY a.created_at DESC
                 LIMIT :n
                """
            ),
            {"uid": user_id, "n": limit},
        )
    ).all()
    return [
        {
            "id": int(r.id),
            "user_id": str(r.user_id),
            "kind": r.kind,
            "payload": dict(r.payload or {}),
            "created_at": r.created_at,
        }
        for r in rows
    ]
