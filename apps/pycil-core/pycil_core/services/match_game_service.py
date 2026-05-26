"""Match-game arcade mode (P7 phase 4).

Pairs N terms with their definitions in randomized order; client tracks
clicks and submits the score. Server returns a fresh deal and persists
the final score for leaderboard purposes.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


DEFAULT_PAIR_COUNT = 6
MAX_PAIR_COUNT = 12


@dataclass
class MatchPair:
    term_id: int
    term_value: str
    definition_id: int
    short_meaning: str


async def deal(
    session: AsyncSession, user_id: UUID, deck_id: UUID, n: int = DEFAULT_PAIR_COUNT
) -> Sequence[MatchPair]:
    n = max(2, min(n, MAX_PAIR_COUNT))
    rows = (
        await session.execute(
            text(
                """
                SELECT t.id AS term_id, t.value AS term_value,
                       d.id AS definition_id, d.canonical_meaning
                  FROM deck_terms dt
                  JOIN terms t ON t.id = dt.term_id
                  JOIN definitions d ON d.term_id = t.id AND d.is_primary
             LEFT JOIN user_term_stats uts
                    ON uts.user_id = :u AND uts.term_id = t.id
                 WHERE dt.deck_id = :d
                   AND COALESCE(uts.status::text, 'active') = 'active'
                 ORDER BY RANDOM()
                 LIMIT :n
                """
            ),
            {"u": user_id, "d": deck_id, "n": n},
        )
    ).all()
    pairs = [
        MatchPair(
            term_id=int(r.term_id),
            term_value=r.term_value,
            definition_id=int(r.definition_id),
            short_meaning=_truncate(r.canonical_meaning, 80),
        )
        for r in rows
    ]
    random.shuffle(pairs)
    return pairs


def _truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 1].rsplit(" ", 1)[0] + "…"
