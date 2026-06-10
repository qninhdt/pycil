"""Async (LLM-judge) grading dispatch.

Shared by the session submit path and the standalone question-check path. For a
``requires_server_grading`` question type, this writes a pending ``responses``
row + a ``grade_answer`` job, enqueues the worker, and returns the ids the client
streams over SSE. ELO/XP is applied later by
``learning_service.apply_async_verdict`` (session flow only) — never here.
"""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.schemas.grading import AsyncGradePending
from pycil_core.services._job_enqueue import enqueue_arq_job


async def enqueue_grade(
    session: AsyncSession,
    *,
    user_id: UUID,
    question_id: UUID,
    user_answer: str,
    session_id: str | None,
) -> AsyncGradePending:
    """Persist a pending response + grade job, enqueue the worker, return ids.

    ``session_id`` is set for the session flow (so ``apply_async_verdict`` can
    re-enter under the session lock) and NULL for the standalone check (no ELO).
    The grade job row carries ``created_by_user_id`` so the SSE ownership gate
    admits only the submitting user.
    """
    job_id = uuid4()
    response_id = uuid4()

    await session.execute(
        text(
            """
            INSERT INTO jobs (id, type, status, payload, created_by_user_id)
            VALUES (:id, 'grade_answer', 'pending', CAST(:payload AS jsonb), :uid)
            """
        ),
        {
            "id": str(job_id),
            "payload": json.dumps(
                {"response_id": str(response_id), "question_id": str(question_id)}
            ),
            "uid": user_id,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO responses (
                id, user_id, question_id, is_correct, user_answer,
                grade_status, session_id, elo_applied
            )
            VALUES (
                :id, :uid, :qid, FALSE, :ua, 'pending', :sid, FALSE
            )
            """
        ),
        {
            "id": str(response_id),
            "uid": user_id,
            "qid": str(question_id),
            "ua": user_answer,
            "sid": session_id,
        },
    )
    await session.commit()

    try:
        await enqueue_arq_job(
            "grade_answer", str(job_id), str(response_id), _job_id=str(job_id)
        )
    except Exception:
        await session.execute(
            text(
                "UPDATE jobs SET status = 'failed', error = 'enqueue_failed',"
                " updated_at = NOW() WHERE id = :id"
            ),
            {"id": str(job_id)},
        )
        await session.execute(
            text("DELETE FROM responses WHERE id = :id"), {"id": str(response_id)}
        )
        await session.commit()
        raise

    return AsyncGradePending(job_id=job_id, response_id=response_id)
