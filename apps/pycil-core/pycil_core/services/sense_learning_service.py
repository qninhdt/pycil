"""Sense-aware learning loop scaffold (P8 phase 4).

Given a user_definition_stats row keyed on (user_id, definition_id),
selects the next sense to study. When a user has multiple senses for a
term, alternates between them so they don't drift to learning only the
primary sense.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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
    rows = (
        await session.execute(
            text(
                """
                SELECT d.id, d.sense_index, d.canonical_meaning,
                       COALESCE(uds.elo, 800) AS elo,
                       uds.last_seen_at
                  FROM definitions d
             LEFT JOIN user_definition_stats uds
                    ON uds.user_id = :u AND uds.definition_id = d.id
                 WHERE d.term_id = :t
                 ORDER BY uds.last_seen_at NULLS FIRST,
                          d.sense_index ASC
                 LIMIT 1
                """
            ),
            {"u": user_id, "t": term_id},
        )
    ).all()
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
    await session.execute(
        text(
            """
            INSERT INTO user_definition_stats
              (user_id, definition_id, elo, total_seen, total_correct, last_seen_at)
            VALUES (:u, :d, :e, 1, :c, NOW())
            ON CONFLICT (user_id, definition_id) DO UPDATE
              SET elo = :e,
                  total_seen = user_definition_stats.total_seen + 1,
                  total_correct = user_definition_stats.total_correct + :c,
                  last_seen_at = NOW()
            """
        ),
        {"u": user_id, "d": definition_id, "e": new_elo, "c": int(is_correct)},
    )


async def list_senses_for_user(
    session: AsyncSession, user_id: UUID, term_id: int
) -> Sequence[SenseCandidate]:
    rows = (
        await session.execute(
            text(
                """
                SELECT d.id, d.sense_index, d.canonical_meaning,
                       COALESCE(uds.elo, 800) AS elo,
                       uds.last_seen_at
                  FROM definitions d
             LEFT JOIN user_definition_stats uds
                    ON uds.user_id = :u AND uds.definition_id = d.id
                 WHERE d.term_id = :t
                 ORDER BY d.is_primary DESC, d.sense_index ASC
                """
            ),
            {"u": user_id, "t": term_id},
        )
    ).all()
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
