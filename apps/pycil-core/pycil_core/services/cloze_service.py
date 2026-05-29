"""Cloze (fill-in-blank) generation from example sentences (P3 phase 6).

Picks a random content word in an example sentence, replaces it with a
gap, and uses the original word as expected_answer. No LLM round trip
needed — pure transformation of existing data.
"""
from __future__ import annotations

import random
import re
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from shared.db import DeckTerm, Definition, TermExampleSentence, UserTermStat
from shared.db.enums import UserTermStatus
from sqlalchemy import and_, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

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
    sentence_subquery = (
        select(TermExampleSentence.value)
        .where(TermExampleSentence.definition_id == Definition.id)
        .order_by(TermExampleSentence.id.asc())
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        select(
            Definition.id.label("definition_id"),
            sentence_subquery.label("sentence"),
        )
        .select_from(DeckTerm)
        .join(
            Definition,
            and_(
                Definition.term_id == DeckTerm.term_id,
                Definition.is_primary.is_(True),
            ),
        )
        .outerjoin(
            UserTermStat,
            and_(
                UserTermStat.user_id == user_id,
                UserTermStat.definition_id == Definition.id,
            ),
        )
        .where(
            DeckTerm.deck_id == deck_id,
            or_(
                UserTermStat.status.is_(None),
                UserTermStat.status == UserTermStatus.ACTIVE,
            ),
        )
        .order_by(UserTermStat.last_review_date.asc().nullsfirst())
        .limit(limit * 2)
    )
    rows = (await session.exec(stmt)).all()
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
