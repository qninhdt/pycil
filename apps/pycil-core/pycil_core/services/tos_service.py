"""ToS + cookie consent service (P12 phases 3-4).

- list_versions / latest: versioned ToS rolled out by admin.
- needs_ack: returns latest version not yet ack'd by the user, if any.
- ack:        records user_tos_acks row (idempotent).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class TosVersion:
    version: str
    summary: str
    body_md: str
    effective_at: datetime


async def latest(session: AsyncSession) -> TosVersion | None:
    row = (
        await session.execute(
            text(
                "SELECT version, summary, body_md, effective_at "
                "FROM tos_versions ORDER BY effective_at DESC LIMIT 1"
            )
        )
    ).first()
    if not row:
        return None
    return TosVersion(
        version=row.version,
        summary=row.summary,
        body_md=row.body_md,
        effective_at=row.effective_at,
    )


async def needs_ack(
    session: AsyncSession, user_id: UUID
) -> TosVersion | None:
    """Returns the latest version that the user has NOT yet ack'd."""
    row = (
        await session.execute(
            text(
                """
                SELECT v.version, v.summary, v.body_md, v.effective_at
                  FROM tos_versions v
             LEFT JOIN user_tos_acks a
                    ON a.user_id = :uid AND a.version = v.version
                 WHERE a.version IS NULL
                 ORDER BY v.effective_at DESC
                 LIMIT 1
                """
            ),
            {"uid": user_id},
        )
    ).first()
    if not row:
        return None
    return TosVersion(
        version=row.version,
        summary=row.summary,
        body_md=row.body_md,
        effective_at=row.effective_at,
    )


async def ack(session: AsyncSession, user_id: UUID, version: str) -> None:
    await session.execute(
        text(
            "INSERT INTO user_tos_acks (user_id, version) "
            "VALUES (:u, :v) "
            "ON CONFLICT DO NOTHING"
        ),
        {"u": user_id, "v": version},
    )
