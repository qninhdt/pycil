"""Term selection for learning sessions.

Per idea.md §4.2: priority order for picking M definitions to study =
  1. Due (`next_review_date <= now`)
  2. New (no `user_term_stats` row)
  3. Upcoming (sorted by `next_review_date` ASC)

Sample only from definitions belonging to the target deck. Recursive folder
walk is v0.2; v1 picks one deck at a time.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def select_definition_ids(
    session: AsyncSession, user_id: UUID, deck_id: UUID, limit: int
) -> list[int]:
    """Return up to `limit` definition_ids for this user × deck.

    The single SQL uses three UNION ALL branches with explicit priority so
    the planner can stop early once `limit` rows are produced.
    """
    rows = (
        await session.execute(
            text(
                """
                WITH deck_defs AS (
                    SELECT dd.definition_id
                    FROM deck_definitions dd
                    WHERE dd.deck_id = :deck
                ),
                ranked AS (
                    -- 1: due
                    SELECT 1 AS prio, d.definition_id, uts.next_review_date AS nrd
                    FROM deck_defs d
                    JOIN user_term_stats uts
                      ON uts.user_id = :uid AND uts.definition_id = d.definition_id
                    WHERE uts.next_review_date IS NOT NULL
                      AND uts.next_review_date <= NOW()
                    UNION ALL
                    -- 2: never reviewed
                    SELECT 2 AS prio, d.definition_id, NULL AS nrd
                    FROM deck_defs d
                    LEFT JOIN user_term_stats uts
                      ON uts.user_id = :uid AND uts.definition_id = d.definition_id
                    WHERE uts.user_id IS NULL
                    UNION ALL
                    -- 3: upcoming
                    SELECT 3 AS prio, d.definition_id, uts.next_review_date AS nrd
                    FROM deck_defs d
                    JOIN user_term_stats uts
                      ON uts.user_id = :uid AND uts.definition_id = d.definition_id
                    WHERE uts.next_review_date IS NOT NULL
                      AND uts.next_review_date > NOW()
                )
                SELECT definition_id FROM ranked
                ORDER BY prio ASC, nrd ASC NULLS LAST, definition_id ASC
                LIMIT :limit
                """
            ),
            {"uid": user_id, "deck": deck_id, "limit": limit},
        )
    ).all()
    return [r.definition_id for r in rows]
