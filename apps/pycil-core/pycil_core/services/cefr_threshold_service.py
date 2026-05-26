"""Custom CEFR mastery thresholds (P10 phase 3).

Lets a user override the default per-CEFR mastery requirement (i.e. how
many correct answers count as "mastered"). Defaults preserved when the
user has no override.
"""
from __future__ import annotations

import json
from typing import Mapping
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


DEFAULT_THRESHOLDS: dict[str, int] = {
    "A1": 5,
    "A2": 6,
    "B1": 7,
    "B2": 8,
    "C1": 9,
    "C2": 10,
}


async def get_thresholds(
    session: AsyncSession, user_id: UUID
) -> dict[str, int]:
    row = (
        await session.execute(
            text("SELECT study_settings FROM users WHERE id = :id"),
            {"id": user_id},
        )
    ).first()
    settings = (row.study_settings or {}) if row else {}
    overrides = settings.get("cefr_mastery", {}) if isinstance(settings, dict) else {}
    return {**DEFAULT_THRESHOLDS, **overrides}


async def set_thresholds(
    session: AsyncSession,
    user_id: UUID,
    thresholds: Mapping[str, int],
) -> None:
    cleaned = {
        k.upper(): max(1, min(50, int(v)))
        for k, v in thresholds.items()
        if k.upper() in DEFAULT_THRESHOLDS
    }
    row = (
        await session.execute(
            text("SELECT study_settings FROM users WHERE id = :id"),
            {"id": user_id},
        )
    ).first()
    settings = dict(row.study_settings or {}) if row else {}
    settings["cefr_mastery"] = cleaned
    await session.execute(
        text("UPDATE users SET study_settings = CAST(:s AS jsonb) WHERE id = :id"),
        {"s": json.dumps(settings, default=str), "id": user_id},
    )
