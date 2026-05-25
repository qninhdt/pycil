"""Per-node share links: create, revoke, resolve.

Tokens are URL-safe, 32-char base64. Read-only access for /share/{token}
which proxies to a snapshot of the node's content.
"""
from __future__ import annotations

import secrets
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _new_token() -> str:
    return secrets.token_urlsafe(24)


async def create_link(
    session: AsyncSession,
    *,
    node_id: UUID,
    created_by: UUID,
) -> dict:
    """Create a fresh share link. Returns the new row."""
    token = _new_token()
    row = (
        await session.execute(
            text(
                """
                INSERT INTO node_share_links (node_id, token, created_by)
                VALUES (:nid, :token, :uid)
                RETURNING id, token, created_at
                """
            ),
            {"nid": node_id, "token": token, "uid": created_by},
        )
    ).one()
    await session.commit()
    return {
        "id": str(row.id),
        "token": row.token,
        "created_at": row.created_at.isoformat(),
    }


async def revoke_link(
    session: AsyncSession,
    *,
    link_id: UUID,
    user_id: UUID,
) -> bool:
    """Revoke a link if owned by user. Returns True if updated."""
    result = await session.execute(
        text(
            """
            UPDATE node_share_links
               SET revoked_at = NOW()
             WHERE id = :lid
               AND created_by = :uid
               AND revoked_at IS NULL
            """
        ),
        {"lid": link_id, "uid": user_id},
    )
    await session.commit()
    return bool(getattr(result, "rowcount", 0))


async def resolve_token(
    session: AsyncSession, *, token: str
) -> dict | None:
    """Return active link details by token, or None if missing/revoked."""
    row = (
        await session.execute(
            text(
                """
                SELECT id, node_id, created_by, created_at
                  FROM node_share_links
                 WHERE token = :token AND revoked_at IS NULL
                 LIMIT 1
                """
            ),
            {"token": token},
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
        await session.execute(
            text(
                """
                SELECT id, token, created_at, revoked_at
                  FROM node_share_links
                 WHERE node_id = :nid AND created_by = :uid
                 ORDER BY created_at DESC
                """
            ),
            {"nid": node_id, "uid": user_id},
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
