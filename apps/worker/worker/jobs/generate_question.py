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

from sqlalchemy import text

from shared.questions.fill_in_blank import FillData, FillInBlankQuestion
from shared.questions.multiple_choice import MCQData, MultipleChoiceQuestion
from shared.questions.write import WriteData, WriteQuestion
from worker.db import SessionLocal
from worker.llm.openrouter import generate_with_schema
from worker.prompts import render
from worker.redis_helpers import add_spend
from worker.sanitize import sanitize_list, sanitize_text


_TYPE_MAP = {
    "MULTIPLE_CHOICE": (MultipleChoiceQuestion, MCQData),
    "WRITE": (WriteQuestion, WriteData),
    "FILL_IN_BLANK": (FillInBlankQuestion, FillData),
}

_log = logging.getLogger(__name__)
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


async def _existing_question_id(session, definition_id: int, q_type: str) -> int | None:
    row = (
        await session.execute(
            text(
                "SELECT id FROM questions "
                "WHERE definition_id = :id AND type = :t "
                "ORDER BY created_at ASC LIMIT 1"
            ),
            {"id": definition_id, "t": q_type},
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


async def generate_question(
    ctx: dict,
    definition_id: int,
    job_id: str,
    difficulty: str = "easy",
    question_type: str = "MULTIPLE_CHOICE",
) -> dict:
    """arq job entrypoint for question generation (MCQ/WRITE/FILL_IN_BLANK)."""
    redis = ctx["redis"]
    job_uuid = UUID(job_id)
    started = time.time()

    if question_type not in _TYPE_MAP:
        raise ValueError(f"unsupported_question_type: {question_type}")
    q_class, schema_cls = _TYPE_MAP[question_type]

    async with SessionLocal() as session:
        existing = await _existing_question_id(session, definition_id, question_type)
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
            if question_type == "MULTIPLE_CHOICE":
                prompt = render(
                    q_class.template_name(),
                    **q_class.prompt_inputs(inputs, difficulty),
                )
            else:
                prompt = render(
                    q_class.template_name(),
                    term_value=inputs["term_value"],
                    definition_text=inputs.get("canonical_meaning") or "",
                )
            output = await generate_with_schema(prompt, schema_cls)
            await add_spend(redis, _ESTIMATED_COST_USD)
            if question_type == "MULTIPLE_CHOICE":
                data = _sanitize_mcq(output)
            else:
                data = output.model_dump()
            row = (
                await session.execute(
                    text(
                        """
                        INSERT INTO questions (definition_id, type, data)
                        VALUES (:did, CAST(:t AS question_type), :data::jsonb)
                        RETURNING id
                        """
                    ),
                    {"did": definition_id, "t": question_type, "data": json.dumps(data)},
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
