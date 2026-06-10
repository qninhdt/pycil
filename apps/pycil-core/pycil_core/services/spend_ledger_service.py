"""LLM spend ledger aggregations (Phase 3, read-only).

All figures are ESTIMATED — `cost_usd` is a flat per-call constant stored by
the worker, not a measured token cost. The metrics page labels them as such.
Pure SELECTs over `llm_spend_events`.
"""
from __future__ import annotations

from datetime import datetime

from shared.db import LlmSpendEvent
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


async def spend_by_day(
    session: AsyncSession, *, start: datetime, end: datetime
) -> list[dict]:
    """Daily total estimated spend + call count for [start, end)."""
    day = func.date_trunc("day", LlmSpendEvent.created_at)
    rows = (
        await session.exec(
            select(
                day.label("day"),
                func.sum(LlmSpendEvent.cost_usd).label("cost_usd"),
                func.count().label("calls"),
            )
            .where(
                LlmSpendEvent.created_at >= start,
                LlmSpendEvent.created_at < end,
            )
            .group_by(day)
            .order_by(day)
        )
    ).all()
    return [
        {
            "day": r.day.date().isoformat() if r.day else None,
            "cost_usd": round(float(r.cost_usd or 0), 6),
            "calls": int(r.calls),
        }
        for r in rows
    ]


async def spend_by_model(
    session: AsyncSession, *, start: datetime, end: datetime
) -> list[dict]:
    """Total estimated spend + call count grouped by model for [start, end)."""
    rows = (
        await session.exec(
            select(
                LlmSpendEvent.model,
                func.sum(LlmSpendEvent.cost_usd).label("cost_usd"),
                func.count().label("calls"),
            )
            .where(
                LlmSpendEvent.created_at >= start,
                LlmSpendEvent.created_at < end,
            )
            .group_by(LlmSpendEvent.model)
            .order_by(func.sum(LlmSpendEvent.cost_usd).desc())
        )
    ).all()
    return [
        {
            "model": r.model,
            "cost_usd": round(float(r.cost_usd or 0), 6),
            "calls": int(r.calls),
        }
        for r in rows
    ]


async def top_spenders(
    session: AsyncSession, *, start: datetime, end: datetime, limit: int = 10
) -> list[dict]:
    """Top-N users by estimated spend for [start, end).

    NOTE: only rows with a non-null `user_id` count — `generate_term` rows are
    intentionally NULL (global/cross-user cached enrichment, red-team F10), so
    they never appear here.
    """
    rows = (
        await session.exec(
            select(
                LlmSpendEvent.user_id,
                func.sum(LlmSpendEvent.cost_usd).label("cost_usd"),
                func.count().label("calls"),
            )
            .where(
                LlmSpendEvent.created_at >= start,
                LlmSpendEvent.created_at < end,
                LlmSpendEvent.user_id.is_not(None),
            )
            .group_by(LlmSpendEvent.user_id)
            .order_by(func.sum(LlmSpendEvent.cost_usd).desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "user_id": str(r.user_id),
            "cost_usd": round(float(r.cost_usd or 0), 6),
            "calls": int(r.calls),
        }
        for r in rows
    ]
