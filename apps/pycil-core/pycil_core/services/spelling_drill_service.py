"""Spelling drill mode (P7 phase 1).

Generates a "type the word from the definition" exercise. Reuses existing
WRITE question pipeline shape but overrides the prompt to surface only the
canonical_meaning + part_of_speech, hiding the term. Marks correctness via
fuzzy match (re-uses answer_grading_service).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.db import DeckTerm, Definition, Term, UserTermStat
from shared.db.enums import UserTermStatus

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
    stmt = (
        select(
            Definition.id.label("definition_id"),
            Definition.term_id,
            Definition.canonical_meaning,
            Definition.part_of_speech.label("pos"),
            Term.value.label("expected"),
        )
        .select_from(DeckTerm)
        .join(Term, Term.id == DeckTerm.term_id)
        .join(
            Definition,
            and_(
                Definition.term_id == Term.id,
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
        .order_by(
            UserTermStat.last_review_date.asc().nullsfirst(),
            DeckTerm.position.asc(),
        )
        .limit(limit)
    )
    rows = (await session.exec(stmt)).all()
    return [
        SpellingPrompt(
            definition_id=int(r.definition_id),
            term_id=int(r.term_id),
            canonical_meaning=r.canonical_meaning or "",
            part_of_speech=r.pos.value if r.pos else "",
            expected=r.expected,
        )
        for r in rows
    ]


def grade_attempt(expected: str, user_answer: str) -> dict:
    return grade(expected=expected, alts=None, user_answer=user_answer)
