"""Multi-sense definition reads (P8 phases 1-2).

Read-side helpers that respect the new sense_index/disambiguator/is_primary
columns. Existing single-sense callers can keep using `primary` and
upgrade incrementally.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from shared.db import Definition
from sqlalchemy import update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


@dataclass
class DefinitionSense:
    id: int
    sense_index: int
    disambiguator: str | None
    is_primary: bool
    canonical_meaning: str
    cefr_level: str | None
    part_of_speech: str | None


async def list_senses(
    session: AsyncSession, term_id: int
) -> Sequence[DefinitionSense]:
    rows = (
        await session.exec(
            select(
                Definition.id,
                Definition.sense_index,
                Definition.disambiguator,
                Definition.is_primary,
                Definition.canonical_meaning,
                Definition.cefr_level,
                Definition.part_of_speech,
            )
            .where(Definition.term_id == term_id)
            .order_by(Definition.is_primary.desc(), Definition.sense_index.asc())
        )
    ).all()
    return [
        DefinitionSense(
            id=int(r.id),
            sense_index=int(r.sense_index),
            disambiguator=r.disambiguator,
            is_primary=bool(r.is_primary),
            canonical_meaning=r.canonical_meaning,
            cefr_level=r.cefr_level.value if r.cefr_level else None,
            part_of_speech=r.part_of_speech.value if r.part_of_speech else None,
        )
        for r in rows
    ]


async def primary(
    session: AsyncSession, term_id: int
) -> DefinitionSense | None:
    row = (
        await session.exec(
            select(
                Definition.id,
                Definition.sense_index,
                Definition.disambiguator,
                Definition.is_primary,
                Definition.canonical_meaning,
                Definition.cefr_level,
                Definition.part_of_speech,
            )
            .where(Definition.term_id == term_id, Definition.is_primary.is_(True))
            .limit(1)
        )
    ).first()
    if not row:
        return None
    return DefinitionSense(
        id=int(row.id),
        sense_index=int(row.sense_index),
        disambiguator=row.disambiguator,
        is_primary=True,
        canonical_meaning=row.canonical_meaning,
        cefr_level=row.cefr_level.value if row.cefr_level else None,
        part_of_speech=row.part_of_speech.value if row.part_of_speech else None,
    )


async def set_primary(
    session: AsyncSession, term_id: int, definition_id: int
) -> None:
    """Flip is_primary to a single sense atomically."""
    await session.exec(
        update(Definition)
        .where(Definition.term_id == term_id)
        .values(is_primary=Definition.id == definition_id)
    )
