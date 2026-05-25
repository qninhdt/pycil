"""Question service: get_or_generate + check_answer.

Cache strategy: SELECT on (definition_id, type='MULTIPLE_CHOICE') LIMIT 1. If
hit → return immediately. Else acquire Redis lock keyed by definition_id and
enqueue `generate_question` arq job.
"""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from arq.connections import RedisSettings, create_pool
from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.config import get_settings
from pycil_core.schemas.question import (
    QuestionCheckResponse,
    QuestionFetchResponse,
    QuestionRead,
)

_LOCK_TTL_SECONDS = 600
_LOCK_LUA = """
local current = redis.call('GET', KEYS[1])
if current then return current end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return ARGV[1]
"""


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


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
        data=data,
        created_at=row.created_at,
    )

async def get_or_generate(
    session: AsyncSession, definition_id: int, difficulty: str
) -> QuestionFetchResponse:
    """Return cached MCQ or fire generation. Difficulty advisory only."""
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "easy"

    # Validate definition exists.
    exists = (
        await session.execute(
            text("SELECT 1 FROM definitions WHERE id = :id"),
            {"id": definition_id},
        )
    ).first()
    if not exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "definition_not_found")

    cached = await _existing_question(session, definition_id)
    if cached is not None:
        return QuestionFetchResponse(question=cached, status="ready")

    redis = _redis()
    try:
        lock_key = f"lock:gen_question:{definition_id}:MCQ"
        new_job_id = str(uuid4())
        result = await redis.eval(
            _LOCK_LUA, 1, lock_key, new_job_id, _LOCK_TTL_SECONDS
        )
        owner_job_id = (
            result.decode() if isinstance(result, bytes) else str(result)
        )

        if owner_job_id == new_job_id:
            await session.execute(
                text(
                    """
                    INSERT INTO jobs (id, type, status, payload)
                    VALUES (:id, 'generate_question', 'pending', :payload::jsonb)
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

            pool = await create_pool(
                RedisSettings.from_dsn(get_settings().redis_url)
            )
            try:
                await pool.enqueue_job(
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
            finally:
                await pool.close()

        return QuestionFetchResponse(status="pending")
    finally:
        await redis.aclose()


async def check_answer(
    session: AsyncSession, question_id: UUID, selected_index: int
) -> QuestionCheckResponse:
    """Validate user's MCQ selection. Imports MCQ class lazily to avoid
    coupling unrelated routes to the shared package import path."""
    from shared.questions.multiple_choice import MultipleChoiceQuestion

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

