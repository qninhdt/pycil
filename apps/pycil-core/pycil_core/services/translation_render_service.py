"""Multi-language definition rendering (P8 phase 8).

User picks an L1 (e.g. vi, es, ja). When set, definition reads return
the canonical English meaning *plus* a translated copy from
`definition_translations(definition_id, locale)`. The translation row
itself is produced by a worker job, not here — this service is the
read-side only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class TranslatedDefinition:
    definition_id: int
    locale: str
    canonical_meaning_translated: str


async def list_translations(
    session: AsyncSession, definition_id: int
) -> Sequence[TranslatedDefinition]:
    try:
        rows = (
            await session.execute(
                text(
                    "SELECT definition_id, locale, canonical_meaning "
                    "FROM definition_translations "
                    "WHERE definition_id = :id"
                ),
                {"id": definition_id},
            )
        ).all()
    except ProgrammingError:
        return []
    return [
        TranslatedDefinition(
            definition_id=int(r.definition_id),
            locale=r.locale,
            canonical_meaning_translated=r.canonical_meaning,
        )
        for r in rows
    ]


async def get_in_locale(
    session: AsyncSession, definition_id: int, locale: str
) -> TranslatedDefinition | None:
    try:
        row = (
            await session.execute(
                text(
                    "SELECT definition_id, locale, canonical_meaning "
                    "FROM definition_translations "
                    "WHERE definition_id = :id AND locale = :loc"
                ),
                {"id": definition_id, "loc": locale.lower()},
            )
        ).first()
    except ProgrammingError:
        return None
    if not row:
        return None
    return TranslatedDefinition(
        definition_id=int(row.definition_id),
        locale=row.locale,
        canonical_meaning_translated=row.canonical_meaning,
    )
