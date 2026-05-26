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
    session: AsyncSession, definition_id: int, difficulty: str, user_id: UUID
) -> QuestionFetchResponse:
    """Return cached MCQ or fire generation. Difficulty advisory only."""
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "easy"

    await _assert_user_can_access_definition(session, definition_id, user_id)

    cached = await _existing_question(session, definition_id)
    if cached is not None:
        return QuestionFetchResponse(question=cached, status="ready")

    redis = _redis()
    try:
        lock_key = f"lock:gen_question:{definition_id}:MCQ"
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
                            "type": "MULTIPLE_CHOICE",
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
    session: AsyncSession, question_id: UUID, selected_index: int, user_id: UUID
) -> QuestionCheckResponse:
    """Validate user's MCQ selection. Imports MCQ class lazily to avoid
    coupling unrelated routes to the shared package import path."""
    from shared.questions.multiple_choice import MultipleChoiceQuestion

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
    if row.type != "MULTIPLE_CHOICE":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported_question_type")

    data = row.data
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (TypeError, ValueError):
            data = {}

    result = MultipleChoiceQuestion.check_answer(
        data, {"selected_index": selected_index}
    )
    correct_idx = data.get("correct_index")
    return QuestionCheckResponse(
        correct=result.correct,
        explanation=result.explanation,
        correct_index=correct_idx if isinstance(correct_idx, int) else 0,
    )

