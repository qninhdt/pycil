"""Spelling drill mode (P7 phase 1).

Generates a "type the word from the definition" exercise. Reuses existing
WRITE question pipeline shape but overrides the prompt to surface only the
canonical_meaning + part_of_speech, hiding the term. Marks correctness via
fuzzy match (re-uses answer_grading_service).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.services.answer_grading_service import grade


@dataclass
class SpellingPrompt:
    definition_id: int
    term_id: int
    canonical_meaning: str
    part_of_speech: str
    expected: str


async def next_prompts(
    session: AsyncSession, user_id: UUID, deck_id: UUID, limit: int = 10
) -> Sequence[SpellingPrompt]:
    rows = (
        await session.execute(
            text(
                """
                SELECT d.id AS definition_id, d.term_id,
                       d.canonical_meaning,
                       d.part_of_speech::text AS pos,
                       t.value AS expected
                  FROM deck_terms dt
                  JOIN terms t ON t.id = dt.term_id
                  JOIN definitions d ON d.term_id = t.id AND d.is_primary
             LEFT JOIN user_term_stats uts
                    ON uts.user_id = :u AND uts.term_id = t.id
                 WHERE dt.deck_id = :d
                   AND COALESCE(uts.status::text, 'active') = 'active'
                 ORDER BY uts.last_seen_at NULLS FIRST, dt.position
                 LIMIT :n
                """
            ),
            {"u": user_id, "d": deck_id, "n": limit},
        )
    ).all()
    return [
        SpellingPrompt(
            definition_id=int(r.definition_id),
            term_id=int(r.term_id),
            canonical_meaning=r.canonical_meaning,
            part_of_speech=r.pos,
            expected=r.expected,
        )
        for r in rows
    ]


def grade_attempt(expected: str, user_answer: str) -> dict:
    return grade(expected=expected, alts=None, user_answer=user_answer)
