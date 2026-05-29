"""Suspend / bury / leech state transitions (P3 phase 3).

Three states:
- active   — included in scheduler
- suspended — user-requested skip; never scheduled
- buried   — auto-skip until `buried_until` date (post-lapse cooldown)

After 5 lapses, auto-suspend (configurable threshold).
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from shared.db import UserTermStat
from shared.db.enums import UserTermStatus
from sqlalchemy import update
from sqlmodel.ext.asyncio.session import AsyncSession

LeechThreshold = 5
BuryDays = 7


async def set_status(
    session: AsyncSession,
    user_id: UUID,
    term_id: int,
    status: UserTermStatus,
    *,
    buried_until: date | None = None,
) -> None:
    await session.exec(
        update(UserTermStat)
        .where(
            UserTermStat.user_id == user_id,
            UserTermStat.definition_id == term_id,
        )
        .values(status=status, buried_until=buried_until)
    )


async def record_lapse(
    session: AsyncSession, user_id: UUID, term_id: int
) -> str:
    """Increment lapse_count and possibly auto-bury or auto-suspend.

    Returns the new status.
    """
    row = (
        await session.exec(
            update(UserTermStat)
            .where(
                UserTermStat.user_id == user_id,
                UserTermStat.definition_id == term_id,
            )
            .values(lapse_count=UserTermStat.lapse_count + 1)
            .returning(UserTermStat.lapse_count)
        )
    ).first()
    if not row:
        return UserTermStatus.ACTIVE.value
    lapse_count = int(row[0] if isinstance(row, tuple) else row.lapse_count)
    if lapse_count >= LeechThreshold:
        await set_status(session, user_id, term_id, UserTermStatus.SUSPENDED)
        return UserTermStatus.SUSPENDED.value
    bury_until = date.today() + timedelta(days=BuryDays)
    await set_status(session, user_id, term_id, UserTermStatus.BURIED, buried_until=bury_until)
    return UserTermStatus.BURIED.value


async def reactivate_buried(session: AsyncSession) -> int:
    """Daily cron — flip buried→active when buried_until <= today."""
    result = await session.exec(
        update(UserTermStat)
        .where(
            UserTermStat.status == UserTermStatus.BURIED,
            UserTermStat.buried_until.is_not(None),
            UserTermStat.buried_until <= date.today(),
        )
        .values(status=UserTermStatus.ACTIVE, buried_until=None)
    )
    return int(getattr(result, "rowcount", 0) or 0)
