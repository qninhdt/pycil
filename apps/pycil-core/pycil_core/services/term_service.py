"""Term service: validate ownership, normalize, upsert.

Phase 2: just creates the term row + deck_definitions placeholder. Phase 3
fires the generate_term job and returns job_id.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.schemas.term import DeckTermRead, TermAddResponse, TermRead


def normalize(value: str) -> str:
    """Lowercase + collapse internal whitespace + strip."""
    return " ".join(value.lower().split())


async def add_term_to_deck(
    session: AsyncSession, user_id: UUID, deck_id: UUID, raw_value: str
) -> TermAddResponse:
    value = normalize(raw_value)
    if not value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "term_empty")
    if "\n" in value or "\r" in value or any(ord(c) < 0x20 for c in value):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "term_control_chars")

    deck_row = (
        await session.execute(
            text(
                "SELECT author_id, type FROM nodes WHERE id = :id"
            ),
            {"id": deck_id},
        )
    ).first()
    if not deck_row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deck_not_found")
    if deck_row.author_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "deck_forbidden")
    if deck_row.type != "DECK":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "node_not_deck")

    # Upsert term (global cache by value).
    upsert = text(
        """
        INSERT INTO terms (value)
        VALUES (:val)
        ON CONFLICT (value) DO NOTHING
        RETURNING id, value, type::text AS type, created_at, updated_at
        """
    )
    term = (await session.execute(upsert, {"val": value})).first()
    if term is None:
        # Existing row — fetch it.
        term = (
            await session.execute(
                text(
                    "SELECT id, value, type::text AS type, created_at, updated_at "
                    "FROM terms WHERE value = :val"
                ),
                {"val": value},
            )
        ).one()

    # Link term to deck. position = current max + 1.
    link = text(
        """
        INSERT INTO deck_terms (deck_id, term_id, position)
        SELECT :deck, :term,
               COALESCE((SELECT MAX(position) + 1 FROM deck_terms WHERE deck_id = :deck), 0)
        ON CONFLICT (deck_id, term_id) DO NOTHING
        RETURNING term_id
        """
    )
    inserted = (
        await session.execute(link, {"deck": deck_id, "term": term.id})
    ).first()
    if inserted is not None:
        # New link → bump deck's count.
        await session.execute(
            text(
                "UPDATE nodes SET definition_count = definition_count + 1, "
                "updated_at = NOW() WHERE id = :id"
            ),
            {"id": deck_id},
        )

    await session.commit()
    return TermAddResponse(
        term=TermRead(
            id=term.id,
            value=term.value,
            type=term.type,
            created_at=term.created_at,
            updated_at=term.updated_at,
        ),
        job_id=None,
    )


async def list_deck_terms(
    session: AsyncSession, user_id: UUID, deck_id: UUID
) -> list[DeckTermRead]:
    """Return ordered terms for a deck with enrichment + job state.

    LEFT JOINs `definitions` (to surface enriched payload) and `user_term_jobs`
    + `jobs` (to surface the SSE handle) so the UI can render skeleton vs
    enriched without a second round-trip.
    """
    deck_row = (
        await session.execute(
            text("SELECT author_id, type FROM nodes WHERE id = :id"),
            {"id": deck_id},
        )
    ).first()
    if not deck_row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deck_not_found")
    if deck_row.author_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "deck_forbidden")

    rows = (
        await session.execute(
            text(
                """
                SELECT
                  t.id, t.value, t.type::text AS type,
                  t.created_at, t.updated_at,
                  dt.position,
                  d.id AS definition_id,
                  d.part_of_speech::text AS part_of_speech,
                  d.cefr_level::text AS cefr_level,
                  d.canonical_meaning,
                  d.synonyms, d.antonyms,
                  utj.job_id, j.status AS job_status
                FROM deck_terms dt
                JOIN terms t ON t.id = dt.term_id
                LEFT JOIN definitions d ON d.term_id = t.id
                LEFT JOIN user_term_jobs utj
                  ON utj.user_id = :uid AND utj.term_id = t.id
                LEFT JOIN jobs j ON j.id = utj.job_id
                WHERE dt.deck_id = :deck
                ORDER BY dt.position ASC, t.created_at ASC
                """
            ),
            {"uid": user_id, "deck": deck_id},
        )
    ).all()

    out: list[DeckTermRead] = []
    for r in rows:
        definition = None
        if r.definition_id is not None:
            definition = {
                "id": r.definition_id,
                "part_of_speech": r.part_of_speech,
                "cefr_level": r.cefr_level,
                "canonical_meaning": r.canonical_meaning,
                "synonyms": r.synonyms,
                "antonyms": r.antonyms,
            }
        out.append(
            DeckTermRead(
                term=TermRead(
                    id=r.id,
                    value=r.value,
                    type=r.type,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                ),
                position=r.position,
                definition=definition,
                job_id=str(r.job_id) if r.job_id else None,
                job_status=r.job_status,
            )
        )
    return out
