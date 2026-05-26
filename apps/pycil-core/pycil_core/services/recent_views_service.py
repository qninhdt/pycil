"""Recently-added + recently-reviewed feeds (P5 phases 3-4)."""
from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def recently_added(
    session: AsyncSession, user_id: UUID, limit: int = 30
) -> Sequence[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT t.id AS term_id, t.value, t.created_at,
                       d.canonical_meaning,
                       n.id AS deck_id, n.name AS deck_name
                  FROM deck_terms dt
                  JOIN terms t ON t.id = dt.term_id
                  JOIN nodes n ON n.id = dt.deck_id
             LEFT JOIN definitions d ON d.term_id = t.id AND d.is_primary
                 WHERE n.author_id = :u
                 ORDER BY t.created_at DESC
                 LIMIT :n
                """
            ),
            {"u": user_id, "n": min(limit, 100)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def recently_reviewed(
    session: AsyncSession, user_id: UUID, limit: int = 30
) -> Sequence[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT t.id AS term_id, t.value,
                       uts.last_seen_at, uts.elo,
                       d.canonical_meaning
                  FROM user_term_stats uts
                  JOIN terms t ON t.id = uts.term_id
             LEFT JOIN definitions d ON d.term_id = t.id AND d.is_primary
                 WHERE uts.user_id = :u
                   AND uts.last_seen_at IS NOT NULL
                 ORDER BY uts.last_seen_at DESC
                 LIMIT :n
                """
            ),
            {"u": user_id, "n": min(limit, 100)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]
