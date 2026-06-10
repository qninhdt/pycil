"""Custom CEFR mastery thresholds.

Lets a user override the default per-CEFR mastery requirement (i.e. how
many correct answers count as "mastered"). Defaults preserved when the
user has no override.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import UUID

from shared.db import User
from sqlalchemy import update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

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
    settings = (
        await session.exec(select(User.study_settings).where(User.id == user_id))
    ).first() or {}
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
    current = (
        await session.exec(select(User.study_settings).where(User.id == user_id))
    ).first()
    settings = dict(current or {})
    settings["cefr_mastery"] = cleaned
    await session.exec(
        update(User)
        .where(User.id == user_id)
        .values(study_settings=json.loads(json.dumps(settings, default=str)))
    )
