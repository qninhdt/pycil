"""Per-node share links: create, revoke, resolve.

Tokens are URL-safe, 32-char base64. Read-only access for /share/{token}
which proxies to a snapshot of the node's content.
"""
from __future__ import annotations

import secrets
from uuid import UUID

from sqlalchemy import delete, func, update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.db import Node, NodeShareLink


def _new_token() -> str:
    return secrets.token_urlsafe(24)


async def create_link(
    session: AsyncSession,
    *,
    node_id: UUID,
    created_by: UUID,
) -> dict:
    """Create a fresh share link. Returns the new row."""
    owns = (
        await session.exec(
            select(Node.id).where(Node.id == node_id, Node.author_id == created_by)
        )
    ).first()
    if owns is None:
        raise LookupError("node_not_found_or_not_owned")
    token = _new_token()
    record = NodeShareLink(node_id=node_id, token=token, created_by=created_by)
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return {
        "id": str(record.id),
        "token": record.token,
        "created_at": record.created_at.isoformat() if record.created_at else "",
    }


async def revoke_link(
    session: AsyncSession,
    *,
    link_id: UUID,
    user_id: UUID,
) -> bool:
    """Revoke a link if owned by user. Returns True if updated."""
    result = await session.exec(
        update(NodeShareLink)
        .where(
            NodeShareLink.id == link_id,
            NodeShareLink.created_by == user_id,
            NodeShareLink.revoked_at.is_(None),
        )
        .values(revoked_at=func.now())
    )
    await session.commit()
    return bool(getattr(result, "rowcount", 0))


async def resolve_token(
    session: AsyncSession, *, token: str
) -> dict | None:
    """Return active link details by token, or None if missing/revoked."""
    row = (
        await session.exec(
            select(
                NodeShareLink.id,
                NodeShareLink.node_id,
                NodeShareLink.created_by,
                NodeShareLink.created_at,
            )
            .where(NodeShareLink.token == token, NodeShareLink.revoked_at.is_(None))
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    return {
        "id": str(row.id),
        "node_id": str(row.node_id),
        "created_by": str(row.created_by),
        "created_at": row.created_at.isoformat(),
    }


async def list_for_node(
    session: AsyncSession,
    *,
    node_id: UUID,
    user_id: UUID,
) -> list[dict]:
    rows = (
        await session.exec(
            select(
                NodeShareLink.id,
                NodeShareLink.token,
                NodeShareLink.created_at,
                NodeShareLink.revoked_at,
            )
            .where(
                NodeShareLink.node_id == node_id,
                NodeShareLink.created_by == user_id,
            )
            .order_by(NodeShareLink.created_at.desc())
        )
    ).all()
    return [
        {
            "id": str(r.id),
            "token": r.token,
            "created_at": r.created_at.isoformat(),
            "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
        }
        for r in rows
    ]
