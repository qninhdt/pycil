"""Background question-bank prewarm (session-triggered).

Fans out generation for terms whose bank depth is below target, so learning
sessions can pull *ready* questions without waiting. Bounded and safe by design:

- **User-attributed:** each generated job carries ``created_by_user_id`` so spend
  is accounted to the triggering user (never NULL — avoids unattributed cap
  drain).
- **Budget-gated:** short-circuits when the daily OpenRouter spend cap is hit.
- **Ceiling-bounded:** processes at most ``_PREWARM_CEILING`` definitions per run
  so a large deck can't flood the queue.
- **One enqueue per ``(definition, type)`` per run:** the per-(definition,type)
  generation lock permits a single in-flight job, so depth accrues across runs
  rather than via a lock-key change. Dropped enqueues are logged (no silent cap).

The call site (enqueue on session start) is wired in the session-integration
phase; this job is the fan-out target.
"""
from __future__ import annotations

import json
import logging
from uuid import uuid4

from sqlalchemy import func
from sqlmodel import select

from shared.db import Question
from shared.db.enums import QuestionType
from worker.config import get_settings
from worker.db import SessionLocal
from worker.redis_helpers import acquire_or_get_lock, get_spend_daily

_log = logging.getLogger(__name__)
_PREWARM_CEILING = 50
_LOCK_TTL_SECONDS = 600


async def _slot_depth(
    session, definition_id: int, q_type: str, difficulty: str
) -> int:
    rows = (
        await session.exec(
            select(Question.id).where(
                Question.definition_id == definition_id,
                Question.type == QuestionType(q_type),
                func.coalesce(Question.data["difficulty"].astext, "") == difficulty,
            )
        )
    ).all()
    return len(rows)


async def prewarm_questions(
    ctx: dict,
    definition_ids: list[int],
    user_id: str,
    difficulty: str = "easy",
    question_type: str = "MULTIPLE_CHOICE",
) -> dict:
    """Enqueue generation for under-target slots among ``definition_ids``."""
    redis = ctx["redis"]
    settings = get_settings()
    target = max(1, settings.question_bank_target_depth)

    spent = await get_spend_daily(redis)
    if spent >= settings.openrouter_budget_daily_usd:
        _log.info(
            "prewarm_skipped_budget",
            extra={"spent": spent, "candidates": len(definition_ids)},
        )
        return {"status": "skipped_budget", "enqueued": 0}

    capped = definition_ids[:_PREWARM_CEILING]
    dropped = len(definition_ids) - len(capped)
    if dropped > 0:
        _log.info("prewarm_ceiling_dropped", extra={"dropped": dropped})

    enqueued = 0
    async with SessionLocal() as session:
        for did in capped:
            if await _slot_depth(session, did, question_type, difficulty) >= target:
                continue
            lock_key = f"lock:gen_question:{did}:{question_type}"
            job_id = str(uuid4())
            holder = await acquire_or_get_lock(
                redis, key=lock_key, value=job_id, ttl_seconds=_LOCK_TTL_SECONDS
            )
            if holder != job_id:
                continue  # generation already in flight for this slot
            await _insert_job(session, job_id, did, difficulty, question_type, user_id)
            await redis.enqueue_job(
                "generate_question",
                did,
                job_id,
                difficulty,
                question_type,
                _job_id=job_id,
            )
            enqueued += 1

    return {"status": "ok", "enqueued": enqueued, "dropped": dropped}


async def _insert_job(
    session, job_id: str, definition_id: int, difficulty: str, q_type: str, user_id: str
) -> None:
    from sqlalchemy import text

    await session.execute(
        text(
            """
            INSERT INTO jobs (id, type, status, payload, created_by_user_id)
            VALUES (:id, 'generate_question', 'pending',
                    CAST(:payload AS jsonb), :uid)
            """
        ),
        {
            "id": job_id,
            "payload": json.dumps(
                {
                    "definition_id": definition_id,
                    "difficulty": difficulty,
                    "type": q_type,
                }
            ),
            "uid": user_id,
        },
    )
    await session.commit()
