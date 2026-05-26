"""Reverse-direction cards (P3 phase 5).

Switches the question prompt: instead of "definition → term", the user
sees the term and selects/types the definition. Re-uses existing
question pipeline by emitting a `direction='reverse'` flag on
question_answers; scheduler treats reverse like a separate facet so
ELO updates don't double-count.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ReversePrompt:
    definition_id: int
    term_value: str
    correct_definition_id: int
    distractors: list[str]


async def build_prompts(
    session: AsyncSession,
    user_id: UUID,
    deck_id: UUID,
    *,
    limit: int = 10,
    distractors_per: int = 3,
) -> Sequence[ReversePrompt]:
    rows = (
        await session.execute(
            text(
                """
                SELECT t.value AS term_value,
                       d.id AS definition_id,
                       d.canonical_meaning
                  FROM deck_terms dt
                  JOIN terms t ON t.id = dt.term_id
                  JOIN definitions d ON d.term_id = t.id AND d.is_primary
             LEFT JOIN user_term_stats uts
                    ON uts.user_id = :u AND uts.term_id = t.id
                 WHERE dt.deck_id = :d
                   AND COALESCE(uts.status::text, 'active') = 'active'
                 ORDER BY uts.last_seen_at NULLS FIRST
                 LIMIT :n
                """
            ),
            {"u": user_id, "d": deck_id, "n": limit},
        )
    ).all()
    if not rows:
        return []

    distractor_rows = (
        await session.execute(
            text(
                """
                SELECT canonical_meaning FROM definitions
                 WHERE is_primary AND id <> ALL(:exclude)
                 ORDER BY RANDOM()
                 LIMIT :n
                """
            ),
            {
                "exclude": [int(r.definition_id) for r in rows],
                "n": len(rows) * distractors_per,
            },
        )
    ).all()
    pool = [r.canonical_meaning for r in distractor_rows]

    out: list[ReversePrompt] = []
    for i, r in enumerate(rows):
        slice_start = i * distractors_per
        slice_end = slice_start + distractors_per
        out.append(
            ReversePrompt(
                definition_id=int(r.definition_id),
                term_value=r.term_value,
                correct_definition_id=int(r.definition_id),
                distractors=pool[slice_start:slice_end],
            )
        )
    return out
