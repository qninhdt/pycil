"""Cloze (fill-in-blank) generation from example sentences (P3 phase 6).

Picks a random content word in an example sentence, replaces it with a
gap, and uses the original word as expected_answer. No LLM round trip
needed — pure transformation of existing data.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_WORD_RE = re.compile(r"\b[a-zA-Z][a-zA-Z'-]{3,}\b")
_STOPWORDS = {
    "the", "and", "with", "that", "this", "from", "have", "been",
    "their", "would", "should", "about", "which", "could", "where",
    "while", "when", "what", "into", "they", "them", "these", "those",
    "your", "ours", "yours", "than", "very", "just", "also",
}


@dataclass
class ClozePrompt:
    definition_id: int
    blanked_sentence: str
    expected: str


def _make_cloze(sentence: str) -> tuple[str, str] | None:
    candidates = [
        m for m in _WORD_RE.finditer(sentence) if m.group(0).lower() not in _STOPWORDS
    ]
    if not candidates:
        return None
    pick = random.choice(candidates)
    expected = pick.group(0)
    blanked = sentence[: pick.start()] + "____" + sentence[pick.end() :]
    return blanked, expected


async def next_prompts(
    session: AsyncSession, user_id: UUID, deck_id: UUID, limit: int = 10
) -> Sequence[ClozePrompt]:
    rows = (
        await session.execute(
            text(
                """
                SELECT d.id AS definition_id,
                       (SELECT value FROM term_example_sentences
                         WHERE definition_id = d.id ORDER BY id ASC LIMIT 1) AS sentence
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
            {"u": user_id, "d": deck_id, "n": limit * 2},
        )
    ).all()
    out: list[ClozePrompt] = []
    for r in rows:
        if not r.sentence:
            continue
        result = _make_cloze(r.sentence)
        if result is None:
            continue
        blanked, expected = result
        out.append(
            ClozePrompt(
                definition_id=int(r.definition_id),
                blanked_sentence=blanked,
                expected=expected,
            )
        )
        if len(out) >= limit:
            break
    return out
