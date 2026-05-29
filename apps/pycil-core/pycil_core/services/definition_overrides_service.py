"""Definition overrides (P8 phase 7).

User-private edits to LLM-generated definitions. Falls back to the
canonical row if no override exists. Stored as a JSON payload so the
shape can evolve without migrations.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.db import DefinitionOverride


async def upsert(
    session: AsyncSession,
    user_id: UUID,
    term_id: int,
    payload: dict[str, Any],
) -> None:
    stmt = insert(DefinitionOverride).values(
        user_id=user_id,
        term_id=term_id,
        payload=json.loads(json.dumps(payload, default=str)),
    )
    await session.exec(
        stmt.on_conflict_do_update(
            index_elements=[DefinitionOverride.user_id, DefinitionOverride.term_id],
            set_={"payload": stmt.excluded.payload},
        )
    )


async def get(
    session: AsyncSession, user_id: UUID, term_id: int
) -> dict[str, Any] | None:
    payload = (
        await session.exec(
            select(DefinitionOverride.payload).where(
                DefinitionOverride.user_id == user_id,
                DefinitionOverride.term_id == term_id,
            )
        )
    ).first()
    return dict(payload or {}) if payload else None


async def delete(
    session: AsyncSession, user_id: UUID, term_id: int
) -> None:
    await session.exec(
        delete(DefinitionOverride).where(
            DefinitionOverride.user_id == user_id,
            DefinitionOverride.term_id == term_id,
        )
    )
