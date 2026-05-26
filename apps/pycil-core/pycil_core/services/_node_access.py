"""Node ownership assertion helper.

Lightweight `nodes.author_id` check — used by routes that already know the
target is a node-id and don't need the full row. node_service._ensure_owner
(which returns the full row) remains the canonical helper for service-layer
code that follows up with mutation.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def assert_node_owner(
    session: AsyncSession, *, node_id: UUID, user_id: UUID
) -> None:
    """Raise 404 if node missing, 403 if not owned by user_id."""
    row = (
        await session.execute(
            text("SELECT author_id FROM nodes WHERE id = :nid"),
            {"nid": node_id},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "node_not_found")
    if row.author_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_owner")
