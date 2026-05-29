"""Term notes (P10 phase 2).

User-private markdown notes attached to a term. Plain CRUD, length-capped,
sanitized at render-time (FE) — server keeps raw markdown.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.db import TermNote

MAX_NOTE_BYTES = 8192


async def upsert(
    session: AsyncSession, user_id: UUID, term_id: int, body: str
) -> str:
    if len(body.encode("utf-8")) > MAX_NOTE_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "term_note_too_large"
        )
    stmt = insert(TermNote).values(user_id=user_id, term_id=term_id, body=body)
    await session.exec(
        stmt.on_conflict_do_update(
            index_elements=[TermNote.user_id, TermNote.term_id],
            set_={"body": stmt.excluded.body},
        )
    )
    return body


async def get(session: AsyncSession, user_id: UUID, term_id: int) -> str | None:
    return (
        await session.exec(
            select(TermNote.body).where(
                TermNote.user_id == user_id,
                TermNote.term_id == term_id,
            )
        )
    ).first()


async def delete(
    session: AsyncSession, user_id: UUID, term_id: int
) -> None:
    await session.exec(
        delete(TermNote).where(
            TermNote.user_id == user_id,
            TermNote.term_id == term_id,
        )
    )
