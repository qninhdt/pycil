"""Definition comments (P9 phase 5).

Threaded discussion attached to a definition row. Soft-delete only —
moderators may flip deleted_at; comments aren't physically removed so
audit trail survives. Body sanitization is FE concern; server caps length
and rate-limits per-user creation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Sequence
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


COMMENT_MAX_BYTES = 4096


async def create(
    session: AsyncSession, author_id: UUID, definition_id: int, body: str
) -> int:
    body = body.strip()
    if not body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "comment_empty")
    if len(body.encode("utf-8")) > COMMENT_MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "comment_too_large"
        )
    row = (
        await session.execute(
            text(
                "INSERT INTO definition_comments (definition_id, author_id, body) "
                "VALUES (:d, :a, :b) RETURNING id"
            ),
            {"d": definition_id, "a": author_id, "b": body},
        )
    ).one()
    return int(row.id)


async def list_for_definition(
    session: AsyncSession, definition_id: int, limit: int = 100
) -> Sequence[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT c.id, c.author_id, c.body, c.created_at,
                       u.username AS author_username
                  FROM definition_comments c
             LEFT JOIN users u ON u.id = c.author_id
                 WHERE c.definition_id = :d
                   AND c.deleted_at IS NULL
                 ORDER BY c.created_at ASC
                 LIMIT :n
                """
            ),
            {"d": definition_id, "n": limit},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def soft_delete(
    session: AsyncSession, comment_id: int, actor_id: UUID
) -> bool:
    """Author or admin can soft-delete. Caller checks admin role."""
    result = await session.execute(
        text(
            """
            UPDATE definition_comments
               SET deleted_at = NOW()
             WHERE id = :id
               AND (author_id = :a OR :a IN (SELECT id FROM users WHERE is_admin))
               AND deleted_at IS NULL
            """
        ),
        {"id": comment_id, "a": actor_id},
    )
    return bool(getattr(result, "rowcount", 0))


async def latest_comment_at(
    session: AsyncSession, definition_id: int
) -> datetime | None:
    row = (
        await session.execute(
            text(
                "SELECT MAX(created_at) AS ts FROM definition_comments "
                "WHERE definition_id = :d AND deleted_at IS NULL"
            ),
            {"d": definition_id},
        )
    ).first()
    return row.ts if row else None
