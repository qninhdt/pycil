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

import logging
import time
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlmodel import select

from shared.db import Definition, DefinitionParaphrase, Job, Question, Term, TermExampleSentence
from shared.db.enums import QuestionType

from shared.questions import registry
from worker.config import get_settings
from worker.db import SessionLocal
from worker.jobs.lifecycle import append_event, is_terminal, mark_job, publish_status
from worker.llm.openrouter import invoke_with_fallback
from worker.observability.spend_ledger import record_spend_event
from worker.observability.spend_metrics import emit_spend
from worker.prompts import render
from worker.redis_helpers import add_spend


_log = logging.getLogger(__name__)
_ESTIMATED_COST_USD = 0.0003


async def _load_inputs(session, definition_id: int) -> dict[str, Any] | None:
    row = (
        await session.exec(
            select(
                Definition.id,
                Definition.cefr_level,
                Definition.part_of_speech,
                Definition.notes,
                Term.value.label("term_value"),
            )
            .select_from(Definition)
            .join(Term, Term.id == Definition.term_id)
            .where(Definition.id == definition_id)
        )
    ).first()
    if not row:
        return None
    paraphrase = (
        await session.exec(
            select(DefinitionParaphrase.value)
            .where(DefinitionParaphrase.definition_id == definition_id)
            .order_by(DefinitionParaphrase.id.asc())
            .limit(1)
        )
    ).first()
    example = (
        await session.exec(
            select(TermExampleSentence.value)
            .where(TermExampleSentence.definition_id == definition_id)
            .order_by(TermExampleSentence.id.asc())
            .limit(1)
        )
    ).first()
    notes = row.notes or []
    canonical = notes[0] if notes else None
    return {
        "term_value": row.term_value,
        "part_of_speech": row.part_of_speech.value if row.part_of_speech else None,
        "cefr_level": row.cefr_level.value if row.cefr_level else None,
        "canonical_meaning": canonical,
        "paraphrase_sample": paraphrase,
        "example_sample": example,
    }


async def _existing_question_id(
    session, definition_id: int, q_type: str
) -> UUID | None:
    return (
        await session.exec(
            select(Question.id)
            .where(
                Question.definition_id == definition_id,
                Question.type == QuestionType(q_type),
            )
            .order_by(Question.created_at.asc())
            .limit(1)
        )
    ).first()


async def _bank_depth(
    session, definition_id: int, q_type: str, difficulty: str
) -> int:
    """Count ready questions for this (definition, type, difficulty) slot.

    Drives the depth-aware skip: generation stops once the bank holds
    TARGET_DEPTH questions for the slot, replacing the old depth-1 cache-hit
    guard so the bank can hold variants without unbounded regeneration.
    """
    rows = (
        await session.exec(
            select(Question.id).where(
                Question.definition_id == definition_id,
                Question.type == QuestionType(q_type),
                func.coalesce(Question.data["difficulty"].astext, "")
                == difficulty,
            )
        )
    ).all()
    return len(rows)


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

    if not registry.is_registered(question_type):
        raise ValueError(f"unsupported_question_type: {question_type}")
    plugin = registry.get(question_type)
    schema_cls = plugin.data_schema

    async with SessionLocal() as gate:
        if await is_terminal(gate, job_id):
            return {"status": "duplicate"}

    async with SessionLocal() as session:
        # Depth-aware skip: stop generating once the bank holds TARGET_DEPTH
        # questions for this (definition, type, difficulty) slot. Replaces the
        # old depth-1 cache-hit guard so the bank can accumulate variants while
        # still bounding regeneration + spend.
        target_depth = max(1, get_settings().question_bank_target_depth)
        depth = await _bank_depth(session, definition_id, question_type, difficulty)
        if depth >= target_depth:
            existing = await _existing_question_id(session, definition_id, question_type)
            await append_event(
                session, job_uuid, {"at": time.time(), "kind": "bank_full"}
            )
            await mark_job(
                session,
                job_uuid,
                status="completed",
                result={"question_id": existing, "cached": True},
            )
            await session.commit()
            await publish_status(
                redis,
                f"results:job_{job_id}",
                {"status": "completed", "question_id": existing},
            )
            return {"status": "completed", "cache_hit": True}

        # created_by_user_id attributes spend to the requesting user (red-team
        # F4/F10). Nullable — older jobs may not carry it.
        job_owner = (
            await session.exec(
                select(Job.created_by_user_id).where(Job.id == job_uuid)
            )
        ).first()

        inputs = await _load_inputs(session, definition_id)
        if inputs is None:
            await mark_job(
                session, job_uuid, status="failed", error="definition_not_found"
            )
            await session.commit()
            await publish_status(
                redis,
                f"results:job_{job_id}",
                {"status": "failed", "error": "definition_not_found"},
            )
            return {"status": "failed"}

        try:
            prompt = render(
                plugin.template_name(),
                **plugin.prompt_inputs(inputs, difficulty),
            )
            fallback = await invoke_with_fallback(prompt, schema_cls)
            output = fallback.output
            await add_spend(redis, _ESTIMATED_COST_USD)
            emit_spend(
                job_id=job_id,
                job_type="generate_question",
                model_used=fallback.model_used,
                cost_usd=_ESTIMATED_COST_USD,
                duration_ms=(time.time() - started) * 1000.0,
            )
            data = plugin.sanitize(output)
            # Difficulty is a bank dimension; persist it so question_bank_service
            # can filter ready questions by requested difficulty.
            data["difficulty"] = difficulty
            question = Question(
                definition_id=definition_id,
                type=QuestionType(question_type),
                data=data,
            )
            session.add(question)
            await session.flush()
            question_id = question.id
            await append_event(
                session,
                job_uuid,
                {
                    "at": time.time(),
                    "kind": "completed",
                    "elapsed": time.time() - started,
                },
            )
            result = {"question_id": question_id, "data": data}
            await mark_job(session, job_uuid, status="completed", result=result)
            await session.commit()
            # Persistent spend ledger — success path only, after persist +
            # commit, idempotent on job_id so a retry never double-counts (F12).
            await record_spend_event(
                user_id=job_owner,
                job_id=job_id,
                job_type="generate_question",
                model=fallback.model_used,
                cost_usd=_ESTIMATED_COST_USD,
            )
            await publish_status(
                redis,
                f"results:job_{job_id}",
                {"status": "completed", **result},
            )
            return {"status": "completed"}
        except Exception as exc:  # noqa: BLE001
            _log.exception("generate_question_failed")
            await session.rollback()
            await append_event(
                session, job_uuid, {"at": time.time(), "kind": "error", "msg": str(exc)[:500]}
            )
            try_n = int(ctx.get("job_try", 1) or 1)
            max_tries = int(ctx.get("max_tries", 1) or 1)
            if try_n >= max_tries:
                await mark_job(
                    session, job_uuid, status="failed", error=str(exc)[:1000]
                )
                await session.commit()
                await publish_status(
                    redis,
                    f"results:job_{job_id}",
                    {"status": "failed", "error": str(exc)[:500]},
                )
            else:
                await session.commit()
            raise
