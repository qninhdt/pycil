"""ToS + cookie consent service (P12 phases 3-4).

- list_versions / latest: versioned ToS rolled out by admin.
- needs_ack: returns latest version not yet ack'd by the user, if any.
- ack:        records user_tos_acks row (idempotent).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.db import TosVersion as TosVersionRecord, UserTosAck


@dataclass
class TosVersion:
    version: str
    summary: str
    body_md: str
    effective_at: datetime


async def latest(session: AsyncSession) -> TosVersion | None:
    row = (
        await session.exec(
            select(
                TosVersionRecord.version,
                TosVersionRecord.summary,
                TosVersionRecord.body_md,
                TosVersionRecord.effective_at,
            )
            .order_by(TosVersionRecord.effective_at.desc())
            .limit(1)
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
        await session.exec(
            select(
                TosVersionRecord.version,
                TosVersionRecord.summary,
                TosVersionRecord.body_md,
                TosVersionRecord.effective_at,
            )
            .outerjoin(
                UserTosAck,
                (UserTosAck.user_id == user_id)
                & (UserTosAck.version == TosVersionRecord.version),
            )
            .where(UserTosAck.version.is_(None))
            .order_by(TosVersionRecord.effective_at.desc())
            .limit(1)
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
    await session.exec(
        insert(UserTosAck)
        .values(user_id=user_id, version=version)
        .on_conflict_do_nothing()
    )
