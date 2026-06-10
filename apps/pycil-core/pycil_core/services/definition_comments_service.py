"""Definition comments.

Threaded discussion attached to a definition row. Soft-delete only —
moderators may flip deleted_at; comments aren't physically removed so
audit trail survives. Body sanitization is FE concern; server caps length
and rate-limits per-user creation.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from shared.db import DefinitionComment, User
from sqlalchemy import func, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

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
    comment = DefinitionComment(
        definition_id=definition_id,
        author_id=author_id,
        body=body,
    )
    session.add(comment)
    await session.flush()
    return int(comment.id or 0)


async def list_for_definition(
    session: AsyncSession, definition_id: int, limit: int = 100
) -> Sequence[dict]:
    stmt = (
        select(
            DefinitionComment.id,
            DefinitionComment.author_id,
            DefinitionComment.body,
            DefinitionComment.created_at,
            User.username.label("author_username"),
        )
        .select_from(DefinitionComment)
        .outerjoin(User, User.id == DefinitionComment.author_id)
        .where(
            DefinitionComment.definition_id == definition_id,
            DefinitionComment.deleted_at.is_(None),
        )
        .order_by(DefinitionComment.created_at.asc())
        .limit(limit)
    )
    rows = (await session.exec(stmt)).all()
    return [dict(r._mapping) for r in rows]


async def soft_delete(
    session: AsyncSession,
    comment_id: int,
    actor_id: UUID,
    *,
    is_admin: bool = False,
) -> bool:
    """Author or admin can soft-delete. Caller checks admin role."""
    conditions = [
        DefinitionComment.id == comment_id,
        DefinitionComment.deleted_at.is_(None),
    ]
    if not is_admin:
        conditions.append(DefinitionComment.author_id == actor_id)
    result = await session.exec(
        update(DefinitionComment)
        .where(*conditions)
        .values(deleted_at=func.now())
    )
    return bool(getattr(result, "rowcount", 0))


async def latest_comment_at(
    session: AsyncSession, definition_id: int
) -> datetime | None:
    return (
        await session.exec(
            select(func.max(DefinitionComment.created_at)).where(
                DefinitionComment.definition_id == definition_id,
                DefinitionComment.deleted_at.is_(None),
            )
        )
    ).one()
