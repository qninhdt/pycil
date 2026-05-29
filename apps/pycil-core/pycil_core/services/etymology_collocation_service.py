"""Etymology + word family (P8 phase 5) and collocations (P8 phase 6).

Bundles two related lookups behind a single service so the FE has one
endpoint per definition. Etymology is denormalized in `definition_etymology`
JSONB column (added by phase 5 migration). Collocations live in a separate
table because there can be many.

These services assume the schema rolls in a future migration; for now
they degrade gracefully (NULL/empty list) when the columns/tables don't
exist yet.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class Etymology:
    origin_language: str | None
    century: str | None
    cognates: list[str]
    note: str | None


async def get_etymology(
    session: AsyncSession, definition_id: int
) -> Etymology | None:
    try:
        row = (
            await session.execute(
                text(
                    "SELECT etymology FROM definitions WHERE id = :id"
                ),
                {"id": definition_id},
            )
        ).first()
    except ProgrammingError:
        return None
    if not row or not row.etymology:
        return None
    payload = row.etymology
    return Etymology(
        origin_language=payload.get("origin_language"),
        century=payload.get("century"),
        cognates=list(payload.get("cognates") or []),
        note=payload.get("note"),
    )


@dataclass
class Collocation:
    pattern: str
    example: str | None


async def list_collocations(
    session: AsyncSession, definition_id: int, limit: int = 12
) -> Sequence[Collocation]:
    try:
        rows = (
            await session.execute(
                text(
                    "SELECT pattern, example FROM definition_collocations "
                    "WHERE definition_id = :id ORDER BY id LIMIT :n"
                ),
                {"id": definition_id, "n": limit},
            )
        ).all()
    except ProgrammingError:
        return []
    return [
        Collocation(pattern=r.pattern, example=r.example) for r in rows
    ]
