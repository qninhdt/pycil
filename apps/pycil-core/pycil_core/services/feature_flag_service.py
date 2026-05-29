"""Feature flags lookup (P6 phase 2).

Two evaluation modes:
- explicit: user_id in `enabled_user_ids` array → enabled.
- percentage: stable hash(user_id) modulo 100 < rollout_percentage → enabled.

Reads cached for 30s in process to avoid hammering Postgres on hot paths.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.db import FeatureFlag

_CACHE_TTL_SECONDS = 30.0


@dataclass
class FlagRecord:
    rollout_percentage: int
    enabled_user_ids: list[UUID]
    payload: dict


_cache: dict[str, tuple[float, FlagRecord | None]] = {}


def _bucket(user_id: UUID, name: str) -> int:
    h = hashlib.sha256(f"{name}:{user_id}".encode()).digest()
    return int.from_bytes(h[:4], "big") % 100


async def _load(session: AsyncSession, name: str) -> FlagRecord | None:
    now = time.monotonic()
    cached = _cache.get(name)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    row = (
        await session.exec(
            select(
                FeatureFlag.rollout_percentage,
                FeatureFlag.enabled_user_ids,
                FeatureFlag.payload,
            ).where(FeatureFlag.name == name)
        )
    ).first()
    record = (
        FlagRecord(
            rollout_percentage=int(row.rollout_percentage),
            enabled_user_ids=list(row.enabled_user_ids or []),
            payload=dict(row.payload or {}),
        )
        if row
        else None
    )
    _cache[name] = (now, record)
    return record


async def is_enabled(
    session: AsyncSession, name: str, user_id: UUID | None = None
) -> bool:
    rec = await _load(session, name)
    if rec is None:
        return False
    if user_id is not None and user_id in rec.enabled_user_ids:
        return True
    if user_id is None:
        return rec.rollout_percentage >= 100
    return _bucket(user_id, name) < rec.rollout_percentage


def invalidate_cache() -> None:
    _cache.clear()
