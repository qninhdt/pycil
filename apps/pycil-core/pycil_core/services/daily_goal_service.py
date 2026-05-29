"""Daily goal + reminder hour persistence (P4 phase 2 + P10 phase 3).

Reads/writes users.daily_goal and users.reminder_hour columns added in
migration 0017. Exposes a helper for "today's progress" summing
question_answers from the user's local-day window.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from shared.db import Response, User
from sqlalchemy import func, update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


@dataclass
class GoalSummary:
    daily_goal: int
    answered_today: int
    correct_today: int
    streak_days: int


async def update_goal(
    session: AsyncSession,
    user_id: UUID,
    *,
    daily_goal: int | None = None,
    reminder_hour: int | None = None,
) -> None:
    if daily_goal is None and reminder_hour is None:
        return
    values: dict[str, int] = {}
    if daily_goal is not None:
        values["daily_goal"] = max(1, min(daily_goal, 500))
    if reminder_hour is not None:
        values["reminder_hour"] = max(0, min(reminder_hour, 23))
    await session.exec(
        update(User).where(User.id == user_id).values(**values)
    )


async def goal_summary(
    session: AsyncSession, user_id: UUID
) -> GoalSummary:
    user_row = (
        await session.exec(
            select(User.daily_goal, User.streak_days).where(User.id == user_id)
        )
    ).first()
    daily_goal = int(user_row.daily_goal) if user_row else 20
    streak = int(getattr(user_row, "streak_days", 0) or 0)

    today_start = datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    counts = (
        await session.exec(
            select(
                func.count(Response.id).label("total"),
                func.count(Response.id)
                .filter(Response.is_correct.is_(True))
                .label("correct"),
            ).where(Response.user_id == user_id, Response.created_at >= today_start)
        )
    ).first()
    return GoalSummary(
        daily_goal=daily_goal,
        answered_today=int(counts.total) if counts else 0,
        correct_today=int(counts.correct) if counts else 0,
        streak_days=streak,
    )
