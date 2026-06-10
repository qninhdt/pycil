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

from fastapi import HTTPException, status
from shared.db import FeatureFlag
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

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


# ── Admin CRUD (Phase 6) — mutators do NOT commit; caller owns the txn ──────


def _validate_rollout(rollout_percentage: int) -> None:
    if not 0 <= rollout_percentage <= 100:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "rollout_out_of_range"
        )


async def list_all(session: AsyncSession) -> list[dict]:
    rows = (
        await session.exec(
            select(
                FeatureFlag.name,
                FeatureFlag.rollout_percentage,
                FeatureFlag.enabled_user_ids,
                FeatureFlag.payload,
                FeatureFlag.updated_at,
            ).order_by(FeatureFlag.name)
        )
    ).all()
    return [
        {
            "name": r.name,
            "rollout_percentage": int(r.rollout_percentage),
            "enabled_user_ids": [str(u) for u in (r.enabled_user_ids or [])],
            "payload": dict(r.payload or {}),
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


async def create(
    session: AsyncSession,
    *,
    name: str,
    rollout_percentage: int,
    enabled_user_ids: list[UUID],
    payload: dict,
    updated_by: UUID,
) -> None:
    """Insert a new flag. 409 if the name already exists. No commit."""
    _validate_rollout(rollout_percentage)
    exists = (
        await session.exec(select(FeatureFlag.name).where(FeatureFlag.name == name))
    ).first()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "flag_exists")
    flag = FeatureFlag(
        name=name,
        rollout_percentage=rollout_percentage,
        enabled_user_ids=enabled_user_ids,
        payload=payload,
        updated_by=updated_by,
    )
    session.add(flag)
    await session.flush()
    invalidate_cache()


async def update_flag(
    session: AsyncSession,
    *,
    name: str,
    rollout_percentage: int | None = None,
    enabled_user_ids: list[UUID] | None = None,
    payload: dict | None = None,
    updated_by: UUID,
) -> None:
    """Partial update of an existing flag (name immutable). 404 if absent. No commit."""
    if rollout_percentage is not None:
        _validate_rollout(rollout_percentage)
    values: dict = {"updated_at": func.now(), "updated_by": updated_by}
    if rollout_percentage is not None:
        values["rollout_percentage"] = rollout_percentage
    if enabled_user_ids is not None:
        values["enabled_user_ids"] = enabled_user_ids
    if payload is not None:
        values["payload"] = payload
    result = await session.exec(
        update(FeatureFlag).where(FeatureFlag.name == name).values(**values)
    )
    if not getattr(result, "rowcount", 0):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "flag_not_found")
    invalidate_cache()


async def delete_flag(session: AsyncSession, *, name: str) -> None:
    """Delete a flag. 404 if absent. No commit."""
    result = await session.exec(
        sa_delete(FeatureFlag).where(FeatureFlag.name == name)
    )
    if not getattr(result, "rowcount", 0):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "flag_not_found")
    invalidate_cache()
