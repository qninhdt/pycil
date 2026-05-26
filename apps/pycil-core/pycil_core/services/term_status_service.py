"""Suspend / bury / leech state transitions (P3 phase 3).

Three states:
- active   — included in scheduler
- suspended — user-requested skip; never scheduled
- buried   — auto-skip until `buried_until` date (post-lapse cooldown)

After 5 lapses, auto-suspend (configurable threshold).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

LeechThreshold = 5
BuryDays = 7

UserTermStatus = Literal["active", "suspended", "buried"]


async def set_status(
    session: AsyncSession,
    user_id: UUID,
    term_id: int,
    status: UserTermStatus,
    *,
    buried_until: date | None = None,
) -> None:
    await session.execute(
        text(
            """
            UPDATE user_term_stats
               SET status = :s,
                   buried_until = :b
             WHERE user_id = :u AND term_id = :t
            """
        ),
        {"s": status, "b": buried_until, "u": user_id, "t": term_id},
    )


async def record_lapse(
    session: AsyncSession, user_id: UUID, term_id: int
) -> UserTermStatus:
    """Increment lapse_count and possibly auto-bury or auto-suspend.

    Returns the new status.
    """
    row = (
        await session.execute(
            text(
                """
                UPDATE user_term_stats
                   SET lapse_count = lapse_count + 1
                 WHERE user_id = :u AND term_id = :t
             RETURNING lapse_count
                """
            ),
            {"u": user_id, "t": term_id},
        )
    ).first()
    if not row:
        return "active"
    if row.lapse_count >= LeechThreshold:
        await set_status(session, user_id, term_id, "suspended")
        return "suspended"
    bury_until = date.today() + timedelta(days=BuryDays)
    await set_status(session, user_id, term_id, "buried", buried_until=bury_until)
    return "buried"


async def reactivate_buried(session: AsyncSession) -> int:
    """Daily cron — flip buried→active when buried_until <= today."""
    result = await session.execute(
        text(
            """
            UPDATE user_term_stats
               SET status = 'active', buried_until = NULL
             WHERE status = 'buried'
               AND buried_until IS NOT NULL
               AND buried_until <= CURRENT_DATE
            """
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)
