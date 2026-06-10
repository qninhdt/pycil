"""Question bank reads for the shared, globally-reused question pool.

The bank is keyed by ``(definition_id, type, difficulty)``. Reads apply the
plugin's ``public_projection`` so answer fields never leak pre-submit — the bank
is global, so a missing projection would expose answers to every user.

Variant rotation prefers the question the requesting user has seen least
(``responses`` join) so repeat sessions don't always serve the same item.
"""
from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.schemas.question import QuestionRead


def _coerce_data(data: object) -> dict:
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


async def bank_depth(
    session: AsyncSession,
    definition_id: int,
    q_type: str,
    difficulty: str,
) -> int:
    """Count ready questions in the (definition, type, difficulty) slot."""
    row = (
        await session.execute(
            text(
                """
                SELECT count(*) AS n
                  FROM questions
                 WHERE definition_id = :did
                   AND type = :qtype
                   AND data->>'difficulty' = :diff
                """
            ),
            {"did": definition_id, "qtype": q_type, "diff": difficulty},
        )
    ).first()
    return int(row.n) if row else 0


async def get_ready(
    session: AsyncSession,
    definition_id: int,
    q_type: str,
    difficulty: str,
    user_id: UUID,
) -> QuestionRead | None:
    """Return a ready question for the slot, or None if the bank is empty.

    Applies ``public_projection`` (answer fields stripped). Difficulty filter
    tolerates rows with a missing/NULL difficulty so legacy data is not orphaned
    before the backfill migration runs. Variant rotation: least-seen-by-user
    first, then oldest.
    """
    from shared.questions import registry

    row = (
        await session.execute(
            text(
                """
                SELECT q.id, q.definition_id, q.type::text AS type, q.data,
                       q.created_at
                  FROM questions q
                 WHERE q.definition_id = :did
                   AND q.type = :qtype
                   AND (q.data->>'difficulty' = :diff
                        OR q.data->>'difficulty' IS NULL)
                 ORDER BY (
                     SELECT count(*) FROM responses r
                      WHERE r.question_id = q.id AND r.user_id = :uid
                 ) ASC, q.created_at ASC
                 LIMIT 1
                """
            ),
            {"did": definition_id, "qtype": q_type, "diff": difficulty, "uid": user_id},
        )
    ).first()
    if not row:
        return None

    data = _coerce_data(row.data)
    # Fail closed: the bank is global and answer-bearing. If the type has no
    # registered plugin we cannot strip answer fields, so refuse to serve it
    # rather than leak correct_index/expected_answer pre-submit.
    if not registry.is_registered(row.type):
        return None
    data = registry.get(row.type).public_projection(data)
    return QuestionRead(
        id=row.id,
        definition_id=row.definition_id,
        type=row.type,
        data=data,
        created_at=row.created_at,
    )


async def gaps_for_term(
    session: AsyncSession,
    definition_id: int,
    q_types: list[str],
    difficulty: str,
    target_depth: int,
) -> list[tuple[str, str]]:
    """Return ``(type, difficulty)`` slots below ``target_depth`` for this term.

    Used by the prewarm enqueue helper to fire generation only for real gaps.
    """
    gaps: list[tuple[str, str]] = []
    for q_type in q_types:
        depth = await bank_depth(session, definition_id, q_type, difficulty)
        if depth < target_depth:
            gaps.append((q_type, difficulty))
    return gaps


async def enqueue_prewarm(
    definition_ids: list[int],
    user_id: UUID,
    difficulty: str = "easy",
    question_type: str = "MULTIPLE_CHOICE",
) -> None:
    """Fire one background ``prewarm_questions`` job for the given terms.

    Thin fan-out trigger: the worker job computes per-slot gaps, budget-gates,
    and enqueues generation with the user attributed for spend. No-op when
    prewarm is disabled or there are no terms. Called on session start.
    """
    from pycil_core.config import get_settings
    from pycil_core.services._job_enqueue import enqueue_arq_job

    settings = get_settings()
    if not settings.question_bank_prewarm_enabled or not definition_ids:
        return
    if question_type not in settings.question_bank_prewarm_types_list:
        return
    await enqueue_arq_job(
        "prewarm_questions",
        definition_ids,
        str(user_id),
        difficulty,
        question_type,
        _job_id=f"prewarm:{user_id}:{question_type}:{difficulty}:{min(definition_ids)}",
    )
