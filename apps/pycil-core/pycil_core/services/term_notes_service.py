"""Term notes (P10 phase 2).

User-private markdown notes attached to a term. Plain CRUD, length-capped,
sanitized at render-time (FE) — server keeps raw markdown.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


MAX_NOTE_BYTES = 8192


async def upsert(
    session: AsyncSession, user_id: UUID, term_id: int, body: str
) -> str:
    if len(body.encode("utf-8")) > MAX_NOTE_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "term_note_too_large"
        )
    await session.execute(
        text(
            """
            INSERT INTO term_notes (user_id, term_id, body)
            VALUES (:u, :t, :b)
            ON CONFLICT (user_id, term_id) DO UPDATE
              SET body = EXCLUDED.body, updated_at = NOW()
            """
        ),
        {"u": user_id, "t": term_id, "b": body},
    )
    return body


async def get(session: AsyncSession, user_id: UUID, term_id: int) -> str | None:
    row = (
        await session.execute(
            text(
                "SELECT body FROM term_notes "
                "WHERE user_id = :u AND term_id = :t"
            ),
            {"u": user_id, "t": term_id},
        )
    ).first()
    return row.body if row else None


async def delete(
    session: AsyncSession, user_id: UUID, term_id: int
) -> None:
    await session.execute(
        text(
            "DELETE FROM term_notes "
            "WHERE user_id = :u AND term_id = :t"
        ),
        {"u": user_id, "t": term_id},
    )
