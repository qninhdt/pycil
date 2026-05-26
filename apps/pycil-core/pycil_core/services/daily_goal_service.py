"""Daily goal + reminder hour persistence (P4 phase 2 + P10 phase 3).

Reads/writes users.daily_goal and users.reminder_hour columns added in
migration 0017. Exposes a helper for "today's progress" summing
question_answers from the user's local-day window.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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
    sets: list[str] = []
    params: dict = {"id": user_id}
    if daily_goal is not None:
        sets.append("daily_goal = :g")
        params["g"] = max(1, min(daily_goal, 500))
    if reminder_hour is not None:
        sets.append("reminder_hour = :h")
        params["h"] = max(0, min(reminder_hour, 23))
    await session.execute(
        text(f"UPDATE users SET {', '.join(sets)} WHERE id = :id"),
        params,
    )


async def goal_summary(
    session: AsyncSession, user_id: UUID
) -> GoalSummary:
    user_row = (
        await session.execute(
            text(
                "SELECT daily_goal, current_streak FROM users WHERE id = :id"
            ),
            {"id": user_id},
        )
    ).first()
    daily_goal = int(user_row.daily_goal) if user_row else 20
    streak = int(getattr(user_row, "current_streak", 0) or 0)

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    counts = (
        await session.execute(
            text(
                """
                SELECT COUNT(*)::int AS total,
                       COUNT(*) FILTER (WHERE is_correct)::int AS correct
                  FROM question_answers
                 WHERE user_id = :u AND answered_at >= :start
                """
            ),
            {"u": user_id, "start": today_start},
        )
    ).first()
    return GoalSummary(
        daily_goal=daily_goal,
        answered_today=int(counts.total) if counts else 0,
        correct_today=int(counts.correct) if counts else 0,
        streak_days=streak,
    )
