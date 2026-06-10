"""Reverse-direction cards (P3 phase 5).

Switches the question prompt: instead of "definition → term", the user
sees the term and selects/types the definition. Re-uses existing
question pipeline by emitting a `direction='reverse'` flag on
question_answers; scheduler treats reverse like a separate facet so
ELO updates don't double-count.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from shared.db import DeckTerm, Definition, Term, UserTermStat
from shared.db.enums import UserTermStatus
from sqlalchemy import and_, func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


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
    stmt = (
        select(
            Term.value.label("term_value"),
            Definition.id.label("definition_id"),
            Definition.canonical_meaning,
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
        .order_by(UserTermStat.last_review_date.asc().nullsfirst())
        .limit(limit)
    )
    rows = (await session.exec(stmt)).all()
    if not rows:
        return []

    distractor_stmt = (
        select(Definition.canonical_meaning)
        .where(
            Definition.is_primary.is_(True),
            Definition.id.not_in([int(r.definition_id) for r in rows]),
        )
        .order_by(func.random())
        .limit(len(rows) * distractors_per)
    )
    distractor_rows = (await session.exec(distractor_stmt)).all()
    pool = [meaning for meaning in distractor_rows if meaning]

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
