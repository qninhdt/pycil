"""Per-user product metrics (P6 phase 4).

Aggregates the things admin dashboard cares about: DAU/WAU, daily LLM
spend, top decks by activity, signup funnel. Read-only — pure SELECT.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class MetricsSnapshot:
    dau: int
    wau: int
    new_signups_today: int
    questions_answered_today: int
    decks_created_today: int


async def snapshot(session: AsyncSession) -> MetricsSnapshot:
    today_start = date.today()
    week_start = today_start - timedelta(days=7)

    dau = (
        await session.execute(
            text(
                "SELECT COUNT(DISTINCT user_id) AS n FROM question_answers "
                "WHERE answered_at >= :d::timestamptz"
            ),
            {"d": today_start},
        )
    ).one()
    wau = (
        await session.execute(
            text(
                "SELECT COUNT(DISTINCT user_id) AS n FROM question_answers "
                "WHERE answered_at >= :d::timestamptz"
            ),
            {"d": week_start},
        )
    ).one()
    signups = (
        await session.execute(
            text(
                "SELECT COUNT(*) AS n FROM users "
                "WHERE created_at >= :d::timestamptz"
            ),
            {"d": today_start},
        )
    ).one()
    answers = (
        await session.execute(
            text(
                "SELECT COUNT(*) AS n FROM question_answers "
                "WHERE answered_at >= :d::timestamptz"
            ),
            {"d": today_start},
        )
    ).one()
    decks = (
        await session.execute(
            text(
                "SELECT COUNT(*) AS n FROM nodes "
                "WHERE type = 'DECK' AND created_at >= :d::timestamptz"
            ),
            {"d": today_start},
        )
    ).one()
    return MetricsSnapshot(
        dau=int(dau.n),
        wau=int(wau.n),
        new_signups_today=int(signups.n),
        questions_answered_today=int(answers.n),
        decks_created_today=int(decks.n),
    )
