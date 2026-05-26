"""Definition overrides (P8 phase 7).

User-private edits to LLM-generated definitions. Falls back to the
canonical row if no override exists. Stored as a JSON payload so the
shape can evolve without migrations.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def upsert(
    session: AsyncSession,
    user_id: UUID,
    term_id: int,
    payload: dict[str, Any],
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO definition_overrides (user_id, term_id, payload)
            VALUES (:u, :t, CAST(:p AS jsonb))
            ON CONFLICT (user_id, term_id) DO UPDATE
              SET payload = EXCLUDED.payload, updated_at = NOW()
            """
        ),
        {"u": user_id, "t": term_id, "p": json.dumps(payload, default=str)},
    )


async def get(
    session: AsyncSession, user_id: UUID, term_id: int
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                "SELECT payload FROM definition_overrides "
                "WHERE user_id = :u AND term_id = :t"
            ),
            {"u": user_id, "t": term_id},
        )
    ).first()
    return dict(row.payload) if row and row.payload else None


async def delete(
    session: AsyncSession, user_id: UUID, term_id: int
) -> None:
    await session.execute(
        text(
            "DELETE FROM definition_overrides "
            "WHERE user_id = :u AND term_id = :t"
        ),
        {"u": user_id, "t": term_id},
    )
