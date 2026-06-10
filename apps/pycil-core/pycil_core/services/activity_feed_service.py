"""Activity feed.

Append-only event log surfaced in the user's home screen and follower
inbox. Minimal helpers — list current user's events, list events from
followees, append a new event from any service that wants to emit.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from shared.db import ActivityEvent, Follow
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


async def append(
    session: AsyncSession,
    user_id: UUID,
    kind: str,
    payload: dict[str, Any] | None = None,
) -> int:
    event = ActivityEvent(
        user_id=user_id,
        kind=kind,
        payload=json.loads(json.dumps(payload or {}, default=str)),
    )
    session.add(event)
    await session.flush()
    return int(event.id or 0)


async def list_for_user(
    session: AsyncSession, user_id: UUID, limit: int = 50
) -> Sequence[dict]:
    rows = (
        await session.exec(
            select(
                ActivityEvent.id,
                ActivityEvent.kind,
                ActivityEvent.payload,
                ActivityEvent.created_at,
            )
            .where(ActivityEvent.user_id == user_id)
            .order_by(ActivityEvent.created_at.desc())
            .limit(limit)
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
        await session.exec(
            select(
                ActivityEvent.id,
                ActivityEvent.user_id,
                ActivityEvent.kind,
                ActivityEvent.payload,
                ActivityEvent.created_at,
            )
            .join(Follow, Follow.followee_id == ActivityEvent.user_id)
            .where(Follow.follower_id == user_id)
            .order_by(ActivityEvent.created_at.desc())
            .limit(limit)
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
