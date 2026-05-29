"""Per-deck search filter (P5 phase 1).

Server-side substring + CEFR/POS/status filter over a single deck. The
multi-deck/global smart-deck path lives in saved_search_service. This is
the simpler endpoint hit from the deck detail view's search box.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class DeckSearchHit:
    term_id: int
    value: str
    canonical_meaning: str | None
    cefr_level: str | None
    part_of_speech: str | None


async def search(
    session: AsyncSession,
    user_id: UUID,
    deck_id: UUID,
    *,
    query: str | None = None,
    cefr_levels: list[str] | None = None,
    parts_of_speech: list[str] | None = None,
    limit: int = 50,
) -> Sequence[DeckSearchHit]:
    parts: list[str] = []
    params: dict = {"u": user_id, "d": deck_id, "n": min(limit, 200)}
    if query:
        parts.append("(t.value ILIKE :q OR d.canonical_meaning ILIKE :q)")
        params["q"] = f"%{query.strip()[:80]}%"
    if cefr_levels:
        parts.append("d.cefr_level::text = ANY(:cefr)")
        params["cefr"] = cefr_levels
    if parts_of_speech:
        parts.append("d.part_of_speech::text = ANY(:pos)")
        params["pos"] = parts_of_speech
    where = " AND ".join(parts) if parts else "TRUE"

    rows = (
        await session.execute(
            text(
                f"""
                SELECT t.id AS term_id, t.value,
                       d.canonical_meaning,
                       d.cefr_level::text AS cefr_level,
                       d.part_of_speech::text AS part_of_speech
                  FROM deck_terms dt
                  JOIN terms t ON t.id = dt.term_id
             LEFT JOIN definitions d ON d.term_id = t.id AND d.is_primary
                 WHERE dt.deck_id = :d
                   AND {where}
                 ORDER BY dt.position
                 LIMIT :n
                """
            ),
            params,
        )
    ).all()
    return [
        DeckSearchHit(
            term_id=int(r.term_id),
            value=r.value,
            canonical_meaning=r.canonical_meaning,
            cefr_level=r.cefr_level,
            part_of_speech=r.part_of_speech,
        )
        for r in rows
    ]
