"""Question service: get_or_generate + check_answer.

Cache strategy: SELECT on (definition_id, type='MULTIPLE_CHOICE') LIMIT 1. If
hit → return immediately. Else acquire Redis lock keyed by definition_id and
enqueue `generate_question` arq job.
"""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.schemas.grading import AsyncGradePending
from pycil_core.schemas.question import (
    QuestionCheckResponse,
    QuestionFetchResponse,
    QuestionRead,
)
from pycil_core.services._job_enqueue import (
    acquire_lock_or_get_owner,
    enqueue_arq_job,
)
from pycil_core.services.redis_pool import get_redis

_LOCK_TTL_SECONDS = 600


def _redis() -> Redis:
    return get_redis()


async def _assert_user_can_access_definition(
    session: AsyncSession, definition_id: int, user_id: UUID
) -> None:
    """Enforce: user is author of, or has PUBLIC visibility on, a deck linking
    this definition. Otherwise 404 to avoid revealing existence."""
    row = (
        await session.execute(
            text(
                """
                SELECT 1
                  FROM deck_definitions dd
                  JOIN nodes n ON n.id = dd.deck_id
                 WHERE dd.definition_id = :did
                   AND (n.author_id = :uid OR n.visibility = 'PUBLIC')
                 LIMIT 1
                """
            ),
            {"did": definition_id, "uid": user_id},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "definition_not_found")


async def _assert_user_can_access_question(
    session: AsyncSession, question_id: UUID, user_id: UUID
) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1
                  FROM questions q
                  JOIN deck_definitions dd ON dd.definition_id = q.definition_id
                  JOIN nodes n ON n.id = dd.deck_id
                 WHERE q.id = :qid
                   AND (n.author_id = :uid OR n.visibility = 'PUBLIC')
                 LIMIT 1
                """
            ),
            {"qid": question_id, "uid": user_id},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "question_not_found")


_ANSWER_FIELDS = ("correct_index", "explanation", "distractor_rationale",
                  "expected_answer", "alt_answers")


def _strip_answer_fields(data: dict) -> dict:
    """Drop fields that reveal the answer pre-submit. Used on every fetch path."""
    if not isinstance(data, dict):
        return data
    return {k: v for k, v in data.items() if k not in _ANSWER_FIELDS}


async def _existing_question(
    session: AsyncSession, definition_id: int
) -> QuestionRead | None:
    row = (
        await session.execute(
            text(
                """
                SELECT id, definition_id, type::text AS type, data, created_at
                FROM questions
                WHERE definition_id = :did AND type = 'MULTIPLE_CHOICE'
                ORDER BY created_at ASC
                LIMIT 1
                """
            ),
            {"did": definition_id},
        )
    ).first()
    if not row:
        return None
    data = row.data
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (TypeError, ValueError):
            data = {}
    return QuestionRead(
        id=row.id,
        definition_id=row.definition_id,
        type=row.type,
        data=_strip_answer_fields(data) if isinstance(data, dict) else data,
        created_at=row.created_at,
    )

async def get_or_generate(
    session: AsyncSession,
    definition_id: int,
    difficulty: str,
    user_id: UUID,
    question_type: str = "MULTIPLE_CHOICE",
) -> QuestionFetchResponse:
    """Return a cached question of the given type or fire generation.

    Difficulty advisory only. ``question_type`` defaults to MCQ so callers that
    only want multiple-choice (test mode, bank prewarm) need not pass it; the
    learn loop threads a deterministic per-definition type so WRITE/FILL_IN_BLANK
    get served too.
    """
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "easy"

    await _assert_user_can_access_definition(session, definition_id, user_id)

    # Bank read first: return a ready question with no enqueue + no wait when
    # the bank has depth. On-demand generation below is the cold-start fallback.
    from pycil_core.services import question_bank_service

    ready = await question_bank_service.get_ready(
        session, definition_id, question_type, difficulty, user_id
    )
    if ready is not None:
        return QuestionFetchResponse(question=ready, status="ready")

    redis = _redis()
    try:
        # Lock key uses the persisted type string so the on-demand path and the
        # background prewarm job (worker/jobs/prewarm_questions.py) share one
        # single-flight lock per (definition, type) slot — preventing duplicate
        # generation + double spend when both fire for the same slot.
        lock_key = f"lock:gen_question:{definition_id}:{question_type}"
        new_job_id, owner_job_id, is_owner = await acquire_lock_or_get_owner(
            redis, lock_key=lock_key, ttl_seconds=_LOCK_TTL_SECONDS
        )

        if is_owner:
            await session.execute(
                text(
                    """
                    INSERT INTO jobs (id, type, status, payload)
                    VALUES (:id, 'generate_question', 'pending', CAST(:payload AS jsonb))
                    """
                ),
                {
                    "id": new_job_id,
                    "payload": json.dumps(
                        {
                            "definition_id": definition_id,
                            "difficulty": difficulty,
                            "type": question_type,
                        }
                    ),
                },
            )
            await session.commit()

            try:
                await enqueue_arq_job(
                    "generate_question",
                    definition_id,
                    new_job_id,
                    difficulty,
                    question_type,
                    _job_id=new_job_id,
                )
            except Exception:
                await redis.delete(lock_key)
                await session.execute(
                    text(
                        "UPDATE jobs SET status = 'failed', error = 'enqueue_failed',"
                        " updated_at = NOW() WHERE id = :id"
                    ),
                    {"id": new_job_id},
                )
                await session.commit()
                raise

        return QuestionFetchResponse(status="pending")
    finally:
        await redis.aclose()


async def check_answer(
    session: AsyncSession,
    question_id: UUID,
    selected_index: int,
    user_id: UUID,
    answer: dict | None = None,
) -> QuestionCheckResponse | AsyncGradePending:
    """Validate an answer via the plugin registry. Sync types grade inline and
    return ``QuestionCheckResponse``; async (``requires_server_grading``) types
    enqueue a grade job and return ``AsyncGradePending`` (no session → no ELO,
    standalone verdict streaming only)."""
    from shared.questions import registry

    from pycil_core.services import async_grade_service

    await _assert_user_can_access_question(session, question_id, user_id)

    row = (
        await session.execute(
            text(
                "SELECT id, type::text AS type, data FROM questions WHERE id = :id"
            ),
            {"id": question_id},
        )
    ).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "question_not_found")
    if not registry.is_registered(row.type):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported_question_type")

    data = row.data
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (TypeError, ValueError):
            data = {}

    plugin = registry.get(row.type)
    if plugin.requires_server_grading:
        user_answer = str((answer or {}).get("user_answer", ""))
        return await async_grade_service.enqueue_grade(
            session,
            user_id=user_id,
            question_id=question_id,
            user_answer=user_answer,
            session_id=None,
        )

    result = plugin.check_answer(
        data, answer if answer is not None else {"selected_index": selected_index}
    )
    correct_idx = result.reveal.get("correct_index")
    if not isinstance(correct_idx, int):
        raw = data.get("correct_index")
        correct_idx = raw if isinstance(raw, int) else 0
    return QuestionCheckResponse(
        correct=result.correct,
        explanation=result.explanation,
        correct_index=correct_idx,
    )

