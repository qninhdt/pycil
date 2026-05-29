"""Saved searches CRUD (P5 phase 2 + P3 phase 4).

Persists CustomStudyFilter instances per user with a friendly name.
Smart-deck UI in the FE renders one chip per saved search. Each chip
runs the same WHERE-builder used by custom-study sessions.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import json

from sqlalchemy import delete, update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from pycil_core.services.custom_study_filter import CustomStudyFilter
from shared.db import SavedSearch as SavedSearchRecord


@dataclass
class SavedSearch:
    id: int
    name: str
    filter: CustomStudyFilter
    updated_at: datetime


async def create(
    session: AsyncSession,
    user_id: UUID,
    name: str,
    filter_: CustomStudyFilter,
) -> int:
    record = SavedSearchRecord(
        user_id=user_id,
        name=name,
        filter_json=json.loads(json.dumps(filter_.to_dict(), default=str)),
    )
    session.add(record)
    await session.flush()
    return int(record.id or 0)


async def list_for_user(
    session: AsyncSession, user_id: UUID
) -> Sequence[SavedSearch]:
    rows = (
        await session.exec(
            select(
                SavedSearchRecord.id,
                SavedSearchRecord.name,
                SavedSearchRecord.filter_json,
                SavedSearchRecord.updated_at,
            )
            .where(SavedSearchRecord.user_id == user_id)
            .order_by(SavedSearchRecord.updated_at.desc())
        )
    ).all()
    return [
        SavedSearch(
            id=int(r.id),
            name=r.name,
            filter=CustomStudyFilter.from_dict(dict(r.filter_json or {})),
            updated_at=r.updated_at,
        )
        for r in rows
    ]


async def update(
    session: AsyncSession,
    user_id: UUID,
    search_id: int,
    *,
    name: str | None = None,
    filter_: CustomStudyFilter | None = None,
) -> bool:
    values: dict[str, object] = {}
    if name is not None:
        values["name"] = name
    if filter_ is not None:
        values["filter_json"] = json.loads(json.dumps(filter_.to_dict(), default=str))
    if not values:
        return False
    result = await session.exec(
        update(SavedSearchRecord)
        .where(SavedSearchRecord.id == search_id, SavedSearchRecord.user_id == user_id)
        .values(**values)
    )
    return bool(getattr(result, "rowcount", 0))


async def delete(
    session: AsyncSession, user_id: UUID, search_id: int
) -> bool:
    result = await session.exec(
        delete(SavedSearchRecord).where(
            SavedSearchRecord.id == search_id,
            SavedSearchRecord.user_id == user_id,
        )
    )
    return bool(getattr(result, "rowcount", 0))
