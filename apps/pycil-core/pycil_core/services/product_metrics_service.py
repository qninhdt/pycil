"""Per-user product metrics (P6 phase 4).

Aggregates the things admin dashboard cares about: DAU/WAU, daily LLM
spend, top decks by activity, signup funnel. Read-only — pure SELECT.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from shared.db import Node, NodeType, Response, User
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


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

    dau = await session.exec(
        select(func.count(func.distinct(Response.user_id))).where(Response.created_at >= today_start)
    )
    wau = await session.exec(
        select(func.count(func.distinct(Response.user_id))).where(Response.created_at >= week_start)
    )
    signups = await session.exec(
        select(func.count()).select_from(User).where(User.created_at >= today_start)
    )
    answers = await session.exec(
        select(func.count()).select_from(Response).where(Response.created_at >= today_start)
    )
    decks = await session.exec(
        select(func.count())
        .select_from(Node)
        .where(Node.type == NodeType.DECK, Node.created_at >= today_start)
    )
    return MetricsSnapshot(
        dau=int(dau.one()),
        wau=int(wau.one()),
        new_signups_today=int(signups.one()),
        questions_answered_today=int(answers.one()),
        decks_created_today=int(decks.one()),
    )


async def signup_funnel(
    session: AsyncSession, *, start: datetime, end: datetime
) -> dict:
    """Signup → activation funnel for [start, end).

    - total_signups: users created in range.
    - activated: of those, how many recorded at least one Response (answered a
      question) — the first meaningful action.
    - activation_rate: activated / total_signups (0.0 when no signups).
    """
    total = int(
        (
            await session.exec(
                select(func.count())
                .select_from(User)
                .where(User.created_at >= start, User.created_at < end)
            )
        ).one()
    )
    activated = int(
        (
            await session.exec(
                select(func.count(func.distinct(User.id)))
                .select_from(User)
                .join(Response, Response.user_id == User.id)
                .where(User.created_at >= start, User.created_at < end)
            )
        ).one()
    )
    rate = round(activated / total, 4) if total else 0.0
    return {
        "total_signups": total,
        "activated": activated,
        "activation_rate": rate,
    }
