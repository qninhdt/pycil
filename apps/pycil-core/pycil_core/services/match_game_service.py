"""Match-game arcade mode (P7 phase 4).

Pairs N terms with their definitions in randomized order; client tracks
clicks and submits the score. Server returns a fresh deal and persists
the final score for leaderboard purposes.
"""
from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.db import DeckTerm, Definition, Term, UserTermStat
from shared.db.enums import UserTermStatus

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
    stmt = (
        select(
            Term.id.label("term_id"),
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
        .order_by(func.random())
        .limit(n)
    )
    rows = (await session.exec(stmt)).all()
    pairs = [
        MatchPair(
            term_id=int(r.term_id),
            term_value=r.term_value,
            definition_id=int(r.definition_id),
            short_meaning=_truncate(r.canonical_meaning or "", 80),
        )
        for r in rows
    ]
    random.shuffle(pairs)
    return pairs


def _truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 1].rsplit(" ", 1)[0] + "…"
