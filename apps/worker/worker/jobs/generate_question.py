"""generate_question arq job (v1: MCQ only).

Pipeline:
  1. Load definition row + parent term + sample paraphrase + sample example.
  2. Cache hit guard: if a `MULTIPLE_CHOICE` question already exists for this
     definition_id, mark job completed from existing data. (UI's get_or_generate
     also short-circuits, but enqueue can race.)
  3. Render `mcq.md` Jinja2 prompt.
  4. ChatOpenAI(...).with_structured_output(MCQData, method='json_mode').
  5. INSERT questions(type='MULTIPLE_CHOICE', definition_id, data).
  6. UPDATE jobs.status='completed', publish results:job_{job_id}.
  7. Lock TTL-only release.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import text

from shared.questions.multiple_choice import MCQData, MultipleChoiceQuestion
from worker.db import SessionLocal
from worker.llm.openrouter import generate_with_schema
from worker.prompts import render
from worker.redis_helpers import add_spend
from worker.sanitize import sanitize_list, sanitize_text

_log = logging.getLogger(__name__)
_RETRY_SUFFIX = "\n\nIMPORTANT: RETURN ONLY VALID JSON MATCHING THE SCHEMA."
_ESTIMATED_COST_USD = 0.0003


async def _load_inputs(session, definition_id: int) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  d.id,
                  d.cefr_level::text AS cefr_level,
                  d.part_of_speech::text AS part_of_speech,
                  d.notes,
                  t.value AS term_value
                FROM definitions d
                JOIN terms t ON t.id = d.term_id
                WHERE d.id = :id
                """
            ),
            {"id": definition_id},
        )
    ).first()
    if not row:
        return None
    paraphrase = (
        await session.execute(
            text(
                "SELECT value FROM definition_paraphrases "
                "WHERE definition_id = :id ORDER BY id ASC LIMIT 1"
            ),
            {"id": definition_id},
        )
    ).first()
    example = (
        await session.execute(
            text(
                "SELECT value FROM term_example_sentences "
                "WHERE definition_id = :id ORDER BY id ASC LIMIT 1"
            ),
            {"id": definition_id},
        )
    ).first()
    notes = row.notes or []
    canonical = notes[0] if notes else None
    return {
        "term_value": row.term_value,
        "part_of_speech": row.part_of_speech,
        "cefr_level": row.cefr_level,
        "canonical_meaning": canonical,
        "paraphrase_sample": paraphrase.value if paraphrase else None,
        "example_sample": example.value if example else None,
    }


async def _existing_question_id(session, definition_id: int) -> int | None:
    row = (
        await session.execute(
            text(
                "SELECT id FROM questions "
                "WHERE definition_id = :id AND type = 'MULTIPLE_CHOICE' "
                "ORDER BY created_at ASC LIMIT 1"
            ),
            {"id": definition_id},
        )
    ).first()
    return row.id if row else None


def _sanitize_mcq(out: MCQData) -> dict[str, Any]:
    """Strip URLs/HTML/control chars from every string field."""
    return {
        "stem": sanitize_text(out.stem),
        "options": sanitize_list(out.options),
        "correct_index": out.correct_index,
        "explanation": sanitize_text(out.explanation),
        "distractor_rationale": sanitize_list(out.distractor_rationale),
    }


async def _append_event(session, job_id: UUID, event: dict[str, Any]) -> None:
    await session.execute(
        text(
            "UPDATE jobs SET events = events || :evt::jsonb, updated_at = NOW() "
            "WHERE id = :id"
        ),
        {"evt": json.dumps(event, default=str), "id": job_id},
    )


async def _mark_job(
    session,
    job_id: UUID,
    *,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    await session.execute(
        text(
            "UPDATE jobs SET status = :s, result = :r, error = :e, updated_at = NOW() "
            "WHERE id = :id"
        ),
        {
            "s": status,
            "r": json.dumps(result, default=str) if result is not None else None,
            "e": error,
            "id": job_id,
        },
    )


async def _invoke_llm(prompt: str) -> MCQData:
    try:
        return await generate_with_schema(prompt, MCQData)
    except (ValidationError, ValueError) as e:
        _log.warning("mcq_validation_retry", extra={"err": str(e)[:300]})
        return await generate_with_schema(prompt + _RETRY_SUFFIX, MCQData)


async def generate_question(
    ctx: dict, definition_id: int, job_id: str, difficulty: str = "easy"
) -> dict:
    """arq job entrypoint for MCQ generation."""
    redis = ctx["redis"]
    job_uuid = UUID(job_id)
    started = time.time()

    async with SessionLocal() as session:
        # Cache hit guard (race-safe with question_service.get_or_generate).
        existing = await _existing_question_id(session, definition_id)
        if existing is not None:
            await _append_event(
                session, job_uuid, {"at": time.time(), "kind": "cache_hit"}
            )
            await _mark_job(
                session,
                job_uuid,
                status="completed",
                result={"question_id": existing, "cached": True},
            )
            await session.commit()
            await redis.publish(
                f"results:job_{job_id}",
                json.dumps(
                    {"status": "completed", "question_id": existing}, default=str
                ),
            )
            return {"status": "completed", "cache_hit": True}

        inputs = await _load_inputs(session, definition_id)
        if inputs is None:
            await _mark_job(
                session, job_uuid, status="failed", error="definition_not_found"
            )
            await session.commit()
            await redis.publish(
                f"results:job_{job_id}",
                json.dumps(
                    {"status": "failed", "error": "definition_not_found"},
                    default=str,
                ),
            )
            return {"status": "failed"}

        try:
            prompt = render(
                MultipleChoiceQuestion.template_name(),
                **MultipleChoiceQuestion.prompt_inputs(inputs, difficulty),
            )
            output = await _invoke_llm(prompt)
            await add_spend(redis, _ESTIMATED_COST_USD)
            data = _sanitize_mcq(output)
            row = (
                await session.execute(
                    text(
                        """
                        INSERT INTO questions (definition_id, type, data)
                        VALUES (:did, 'MULTIPLE_CHOICE', :data::jsonb)
                        RETURNING id
                        """
                    ),
                    {"did": definition_id, "data": json.dumps(data)},
                )
            ).one()
            question_id = row.id
            await _append_event(
                session,
                job_uuid,
                {
                    "at": time.time(),
                    "kind": "completed",
                    "elapsed": time.time() - started,
                },
            )
            result = {"question_id": question_id, "data": data}
            await _mark_job(session, job_uuid, status="completed", result=result)
            await session.commit()
            await redis.publish(
                f"results:job_{job_id}",
                json.dumps({"status": "completed", **result}, default=str),
            )
            return {"status": "completed"}
        except Exception as exc:  # noqa: BLE001
            _log.exception("generate_question_failed")
            await session.rollback()
            await _append_event(
                session, job_uuid, {"at": time.time(), "kind": "error", "msg": str(exc)[:500]}
            )
            try_n = int(ctx.get("job_try", 1) or 1)
            max_tries = int(ctx.get("max_tries", 1) or 1)
            if try_n >= max_tries:
                await _mark_job(
                    session, job_uuid, status="failed", error=str(exc)[:1000]
                )
                await session.commit()
                await redis.publish(
                    f"results:job_{job_id}",
                    json.dumps({"status": "failed", "error": str(exc)[:500]}),
                )
            else:
                await session.commit()
            raise
