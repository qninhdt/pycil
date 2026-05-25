"""generate_term arq job.

Pipeline:
  1. Load term row.
  2. Pre-INSERT idempotency: if definitions(term_id) already exists, skip
     LLM and just publish completion from existing data.
  3. Render Jinja2 prompt with sanitized term_value inside <USER_TERM> fences.
  4. ChatOpenAI(...).with_structured_output(...).ainvoke(prompt).
     On parse fail → retry once with stricter "RETURN ONLY VALID JSON" suffix.
  5. Sanitize all output string fields.
  6. INSERT definitions / definition_paraphrases / term_example_sentences
     (UNIQUE(term_id) absorbs concurrent retries).
  7. Translate any deck_terms(term_id) rows into deck_definitions.
  8. Append event to jobs.events; UPDATE jobs.status='completed'.
  9. Track spend; PUBLISH results:{term_id}.
 10. Lock TTL-only release — never deleted in finally.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import text

from worker.db import SessionLocal
from worker.llm.openrouter import generate_term_payload
from worker.prompts import render
from worker.redis_helpers import add_spend
from worker.sanitize import sanitize_list, sanitize_text
from worker.schemas.term_generation import TermGenerationOutput

_log = logging.getLogger(__name__)
_RETRY_SUFFIX = "\n\nIMPORTANT: RETURN ONLY VALID JSON MATCHING THE SCHEMA."
# Cost estimate for openai/gpt-4o-mini ≈ $0.0005 per term generation.
_ESTIMATED_COST_USD = 0.0005


async def _existing_definition_id(session, term_id: int) -> int | None:
    row = (
        await session.execute(
            text("SELECT id FROM definitions WHERE term_id = :tid"),
            {"tid": term_id},
        )
    ).first()
    return row.id if row else None


async def _publish_event(redis, term_id: int, payload: dict[str, Any]) -> None:
    await redis.publish(f"results:{term_id}", json.dumps(payload, default=str))


async def _append_job_event(session, job_id: UUID, event: dict[str, Any]) -> None:
    await session.execute(
        text(
            "UPDATE jobs SET events = events || :evt::jsonb, updated_at = NOW() "
            "WHERE id = :id"
        ),
        {"evt": json.dumps(event, default=str), "id": job_id},
    )


async def _mark_job(
    session, job_id: UUID, *, status: str, result: dict | None = None, error: str | None = None
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


async def _invoke_llm(prompt: str) -> TermGenerationOutput:
    """LLM call with one stricter retry on parse/validation failure."""
    try:
        return await generate_term_payload(prompt)
    except (ValidationError, ValueError) as e:
        _log.warning("llm_validation_failed_retry", extra={"err": str(e)[:300]})
        return await generate_term_payload(prompt + _RETRY_SUFFIX)


async def _persist_definition(
    session, term_id: int, output: TermGenerationOutput
) -> int:
    """INSERT definitions/paraphrases/examples. UNIQUE(term_id) absorbs retries."""
    canonical = sanitize_text(output.definition.canonical_meaning)
    notes = [canonical]  # Backward-compat: keep notes[0] for one release.
    insert_def = text(
        """
        INSERT INTO definitions (
            term_id, cefr_level, part_of_speech, synonyms, antonyms, notes,
            canonical_meaning
        )
        VALUES (
            :tid, :cefr::cefr_level, :pos::part_of_speech,
            :syn, :ant, :notes, :canonical
        )
        ON CONFLICT (term_id) DO UPDATE
          SET canonical_meaning = EXCLUDED.canonical_meaning,
              notes = EXCLUDED.notes,
              updated_at = NOW()
        RETURNING id
        """
    )
    def_row = (
        await session.execute(
            insert_def,
            {
                "tid": term_id,
                "cefr": output.definition.cefr_level,
                "pos": output.definition.part_of_speech.value,
                "syn": sanitize_list(output.definition.synonyms),
                "ant": sanitize_list(output.definition.antonyms),
                "notes": notes,
                "canonical": canonical,
            },
        )
    ).one()
    def_id = def_row.id

    for p in output.paraphrases:
        await session.execute(
            text(
                "INSERT INTO definition_paraphrases (definition_id, value, cefr_level) "
                "VALUES (:did, :val, :cefr::cefr_level)"
            ),
            {"did": def_id, "val": sanitize_text(p.value), "cefr": p.cefr_level},
        )
    for ex in output.examples:
        await session.execute(
            text(
                "INSERT INTO term_example_sentences (definition_id, value, cefr_level) "
                "VALUES (:did, :val, :cefr::cefr_level)"
            ),
            {"did": def_id, "val": sanitize_text(ex.value), "cefr": ex.cefr_level},
        )
    return def_id


async def _backfill_deck_definitions(session, term_id: int, definition_id: int) -> None:
    """Translate every deck_terms(term_id) row → deck_definitions row."""
    await session.execute(
        text(
            """
            INSERT INTO deck_definitions (deck_id, definition_id, position)
            SELECT dt.deck_id, :did, dt.position
            FROM deck_terms dt
            WHERE dt.term_id = :tid
            ON CONFLICT (deck_id, definition_id) DO NOTHING
            """
        ),
        {"did": definition_id, "tid": term_id},
    )


async def _build_payload(session, term_id: int, definition_id: int) -> dict:
    """Read enriched data back as the SSE payload."""
    def_row = (
        await session.execute(
            text(
                """
                SELECT id, cefr_level::text AS cefr_level,
                       part_of_speech::text AS part_of_speech,
                       synonyms, antonyms, notes
                FROM definitions WHERE id = :id
                """
            ),
            {"id": definition_id},
        )
    ).one()
    paraphrases = (
        await session.execute(
            text(
                "SELECT value, cefr_level::text AS cefr_level "
                "FROM definition_paraphrases WHERE definition_id = :id"
            ),
            {"id": definition_id},
        )
    ).all()
    examples = (
        await session.execute(
            text(
                "SELECT value, cefr_level::text AS cefr_level "
                "FROM term_example_sentences WHERE definition_id = :id"
            ),
            {"id": definition_id},
        )
    ).all()
    return {
        "term_id": term_id,
        "definition": dict(def_row._mapping),
        "paraphrases": [dict(r._mapping) for r in paraphrases],
        "examples": [dict(r._mapping) for r in examples],
    }


async def generate_term(ctx: dict, term_id: int, job_id: str) -> dict:
    """arq job entrypoint. ctx holds redis client; bind via WorkerSettings."""
    redis = ctx["redis"]
    job_uuid = UUID(job_id)
    started = time.time()

    async with SessionLocal() as session:
        term_row = (
            await session.execute(
                text("SELECT id, value FROM terms WHERE id = :id"),
                {"id": term_id},
            )
        ).first()
        if not term_row:
            await _mark_job(session, job_uuid, status="failed", error="term_not_found")
            await session.commit()
            await _publish_event(
                redis, term_id, {"status": "failed", "error": "term_not_found"}
            )
            return {"status": "failed"}

        # Pre-INSERT idempotency: if definition exists, skip LLM.
        existing = await _existing_definition_id(session, term_id)
        if existing is not None:
            # Cross-user same-term: user B's deck_terms row landed after user A's
            # enrichment. Translate any pending deck_terms → deck_definitions
            # before publishing so all decks see the enriched payload.
            await _backfill_deck_definitions(session, term_id, existing)
            payload = await _build_payload(session, term_id, existing)
            await _append_job_event(
                session, job_uuid, {"at": time.time(), "kind": "cache_hit"}
            )
            await _mark_job(session, job_uuid, status="completed", result=payload)
            await session.commit()
            await _publish_event(redis, term_id, {"status": "completed", **payload})
            return {"status": "completed", "cache_hit": True}

        try:
            prompt = render(
                "generate_term.md", term_value=sanitize_text(term_row.value)
            )
            output = await _invoke_llm(prompt)
            await add_spend(redis, _ESTIMATED_COST_USD)
            definition_id = await _persist_definition(session, term_id, output)
            await _backfill_deck_definitions(session, term_id, definition_id)
            payload = await _build_payload(session, term_id, definition_id)
            await _append_job_event(
                session,
                job_uuid,
                {
                    "at": time.time(),
                    "kind": "completed",
                    "elapsed": time.time() - started,
                },
            )
            await _mark_job(session, job_uuid, status="completed", result=payload)
            await session.commit()
            await _publish_event(redis, term_id, {"status": "completed", **payload})
            return {"status": "completed"}
        except Exception as exc:  # noqa: BLE001
            _log.exception("generate_term_failed", extra={"term_id": term_id})
            await session.rollback()
            await _append_job_event(
                session, job_uuid, {"at": time.time(), "kind": "error", "msg": str(exc)[:500]}
            )
            # Only flip the row to terminal `failed` (and notify SSE) on the
            # last attempt. Earlier attempts re-raise so arq can retry; if we
            # marked failed here, the client would close the stream prematurely.
            try_n = int(ctx.get("job_try", 1) or 1)
            max_tries = int(ctx.get("max_tries", 1) or 1)
            if try_n >= max_tries:
                await _mark_job(
                    session, job_uuid, status="failed", error=str(exc)[:1000]
                )
                await session.commit()
                await _publish_event(
                    redis, term_id, {"status": "failed", "error": str(exc)[:500]}
                )
            else:
                await session.commit()
            # Re-raise so arq counts the retry attempt.
            raise

    # NOTE: lock is intentionally NOT deleted here. TTL-only release.
