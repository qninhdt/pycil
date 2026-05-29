"""Recently-added + recently-reviewed feeds (P5 phases 3-4)."""
from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from shared.db import DeckTerm, Definition, Node, Term, UserTermStat
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


async def recently_added(
    session: AsyncSession, user_id: UUID, limit: int = 30
) -> Sequence[dict]:
    rows = (
        await session.exec(
            select(
                Term.id.label("term_id"),
                Term.value,
                Term.created_at,
                Definition.canonical_meaning,
                Node.id.label("deck_id"),
                Node.name.label("deck_name"),
            )
            .join(DeckTerm, DeckTerm.term_id == Term.id)
            .join(Node, Node.id == DeckTerm.deck_id)
            .outerjoin(Definition, (Definition.term_id == Term.id) & (Definition.is_primary.is_(True)))
            .where(Node.author_id == user_id)
            .order_by(Term.created_at.desc())
            .limit(min(limit, 100))
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def recently_reviewed(
    session: AsyncSession, user_id: UUID, limit: int = 30
) -> Sequence[dict]:
    rows = (
        await session.exec(
            select(
                Term.id.label("term_id"),
                Term.value,
                UserTermStat.last_review_date.label("last_seen_at"),
                UserTermStat.mastery_score.label("elo"),
                Definition.canonical_meaning,
            )
            .join(Definition, Definition.id == UserTermStat.definition_id)
            .join(Term, Term.id == Definition.term_id)
            .where(
                UserTermStat.user_id == user_id,
                UserTermStat.last_review_date.is_not(None),
            )
            .order_by(UserTermStat.last_review_date.desc())
            .limit(min(limit, 100))
        )
    ).all()
    return [dict(r._mapping) for r in rows]
