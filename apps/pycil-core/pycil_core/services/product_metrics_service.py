"""Per-user product metrics (P6 phase 4).

Aggregates the things admin dashboard cares about: DAU/WAU, daily LLM
spend, top decks by activity, signup funnel. Read-only — pure SELECT.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.db import Node, NodeType, Response, User


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
