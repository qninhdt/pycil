"""Multi-sense definition reads (P8 phases 1-2).

Read-side helpers that respect the new sense_index/disambiguator/is_primary
columns. Existing single-sense callers can keep using `primary` and
upgrade incrementally.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class DefinitionSense:
    id: int
    sense_index: int
    disambiguator: str | None
    is_primary: bool
    canonical_meaning: str
    cefr_level: str
    part_of_speech: str


async def list_senses(
    session: AsyncSession, term_id: int
) -> Sequence[DefinitionSense]:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, sense_index, disambiguator, is_primary,
                       canonical_meaning,
                       cefr_level::text AS cefr_level,
                       part_of_speech::text AS part_of_speech
                  FROM definitions
                 WHERE term_id = :tid
                 ORDER BY is_primary DESC, sense_index ASC
                """
            ),
            {"tid": term_id},
        )
    ).all()
    return [
        DefinitionSense(
            id=int(r.id),
            sense_index=int(r.sense_index),
            disambiguator=r.disambiguator,
            is_primary=bool(r.is_primary),
            canonical_meaning=r.canonical_meaning,
            cefr_level=r.cefr_level,
            part_of_speech=r.part_of_speech,
        )
        for r in rows
    ]


async def primary(
    session: AsyncSession, term_id: int
) -> DefinitionSense | None:
    row = (
        await session.execute(
            text(
                """
                SELECT id, sense_index, disambiguator, is_primary,
                       canonical_meaning,
                       cefr_level::text AS cefr_level,
                       part_of_speech::text AS part_of_speech
                  FROM definitions
                 WHERE term_id = :tid AND is_primary
                 LIMIT 1
                """
            ),
            {"tid": term_id},
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
        cefr_level=row.cefr_level,
        part_of_speech=row.part_of_speech,
    )


async def set_primary(
    session: AsyncSession, term_id: int, definition_id: int
) -> None:
    """Flip is_primary to a single sense atomically."""
    await session.execute(
        text(
            "UPDATE definitions SET is_primary = (id = :did) "
            "WHERE term_id = :tid"
        ),
        {"tid": term_id, "did": definition_id},
    )
