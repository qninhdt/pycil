"""Sense-aware learning loop scaffold (P8 phase 4).

Given a user_definition_stats row keyed on (user_id, definition_id),
selects the next sense to study. When a user has multiple senses for a
term, alternates between them so they don't drift to learning only the
primary sense.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from shared.db import Definition, UserDefinitionStat
from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlmodel.ext.asyncio.session import AsyncSession


@dataclass
class SenseCandidate:
    definition_id: int
    sense_index: int
    elo: int
    last_seen_at: object | None
    canonical_meaning: str


async def next_sense_for_term(
    session: AsyncSession, user_id: UUID, term_id: int
) -> SenseCandidate | None:
    stmt = (
        select(
            Definition.id,
            Definition.sense_index,
            Definition.canonical_meaning,
            func.coalesce(UserDefinitionStat.elo, 800).label("elo"),
            UserDefinitionStat.last_seen_at,
        )
        .select_from(Definition)
        .outerjoin(
            UserDefinitionStat,
            and_(
                UserDefinitionStat.user_id == user_id,
                UserDefinitionStat.definition_id == Definition.id,
            ),
        )
        .where(Definition.term_id == term_id)
        .order_by(
            UserDefinitionStat.last_seen_at.asc().nullsfirst(),
            Definition.sense_index.asc(),
        )
        .limit(1)
    )
    rows = (await session.exec(stmt)).all()
    if not rows:
        return None
    r = rows[0]
    return SenseCandidate(
        definition_id=int(r.id),
        sense_index=int(r.sense_index),
        elo=int(r.elo),
        last_seen_at=r.last_seen_at,
        canonical_meaning=r.canonical_meaning,
    )


async def update_sense_stats(
    session: AsyncSession,
    user_id: UUID,
    definition_id: int,
    *,
    is_correct: bool,
    new_elo: int,
) -> None:
    await session.exec(
        insert(UserDefinitionStat)
        .values(
            user_id=user_id,
            definition_id=definition_id,
            elo=new_elo,
            total_seen=1,
            total_correct=int(is_correct),
            last_seen_at=func.now(),
        )
        .on_conflict_do_update(
            index_elements=[
                UserDefinitionStat.user_id,
                UserDefinitionStat.definition_id,
            ],
            set_={
                "elo": new_elo,
                "total_seen": UserDefinitionStat.total_seen + 1,
                "total_correct": UserDefinitionStat.total_correct
                + int(is_correct),
                "last_seen_at": func.now(),
            },
        )
    )


async def list_senses_for_user(
    session: AsyncSession, user_id: UUID, term_id: int
) -> Sequence[SenseCandidate]:
    stmt = (
        select(
            Definition.id,
            Definition.sense_index,
            Definition.canonical_meaning,
            func.coalesce(UserDefinitionStat.elo, 800).label("elo"),
            UserDefinitionStat.last_seen_at,
        )
        .select_from(Definition)
        .outerjoin(
            UserDefinitionStat,
            and_(
                UserDefinitionStat.user_id == user_id,
                UserDefinitionStat.definition_id == Definition.id,
            ),
        )
        .where(Definition.term_id == term_id)
        .order_by(Definition.is_primary.desc(), Definition.sense_index.asc())
    )
    rows = (await session.exec(stmt)).all()
    return [
        SenseCandidate(
            definition_id=int(r.id),
            sense_index=int(r.sense_index),
            elo=int(r.elo),
            last_seen_at=r.last_seen_at,
            canonical_meaning=r.canonical_meaning,
        )
        for r in rows
    ]
