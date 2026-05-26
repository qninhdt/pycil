"""Saved searches CRUD (P5 phase 2 + P3 phase 4).

Persists CustomStudyFilter instances per user with a friendly name.
Smart-deck UI in the FE renders one chip per saved search. Each chip
runs the same WHERE-builder used by custom-study sessions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.services.custom_study_filter import CustomStudyFilter


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
    import json

    row = (
        await session.execute(
            text(
                "INSERT INTO saved_searches (user_id, name, filter_json) "
                "VALUES (:u, :n, CAST(:f AS jsonb)) RETURNING id"
            ),
            {"u": user_id, "n": name, "f": json.dumps(filter_.to_dict(), default=str)},
        )
    ).one()
    return int(row.id)


async def list_for_user(
    session: AsyncSession, user_id: UUID
) -> Sequence[SavedSearch]:
    rows = (
        await session.execute(
            text(
                "SELECT id, name, filter_json, updated_at FROM saved_searches "
                "WHERE user_id = :u ORDER BY updated_at DESC"
            ),
            {"u": user_id},
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
    import json

    sets: list[str] = []
    params: dict = {"u": user_id, "id": search_id}
    if name is not None:
        sets.append("name = :n")
        params["n"] = name
    if filter_ is not None:
        sets.append("filter_json = CAST(:f AS jsonb)")
        params["f"] = json.dumps(filter_.to_dict(), default=str)
    if not sets:
        return False
    sets.append("updated_at = NOW()")
    result = await session.execute(
        text(
            f"UPDATE saved_searches SET {', '.join(sets)} "
            "WHERE id = :id AND user_id = :u"
        ),
        params,
    )
    return bool(getattr(result, "rowcount", 0))


async def delete(
    session: AsyncSession, user_id: UUID, search_id: int
) -> bool:
    result = await session.execute(
        text(
            "DELETE FROM saved_searches WHERE id = :id AND user_id = :u"
        ),
        {"id": search_id, "u": user_id},
    )
    return bool(getattr(result, "rowcount", 0))
