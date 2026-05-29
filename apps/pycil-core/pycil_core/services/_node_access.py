"""Node ownership assertion helper.

Lightweight `nodes.author_id` check — used by routes that already know the
target is a node-id and don't need the full row. node_service._ensure_owner
(which returns the full row) remains the canonical helper for service-layer
code that follows up with mutation.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from shared.db import Node
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


async def assert_node_owner(
    session: AsyncSession, *, node_id: UUID, user_id: UUID
) -> None:
    """Raise 404 if node missing, 403 if not owned by user_id."""
    owner_id = (
        await session.exec(select(Node.author_id).where(Node.id == node_id))
    ).first()
    if owner_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "node_not_found")
    if owner_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_owner")
