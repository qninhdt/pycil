"""translate_definition arq job.

Reads a definition, calls OpenRouter with the translate prompt for the
target language, persists result into `definitions.translation` JSONB
keyed by lang code, publishes terminal SSE frame.
"""
from __future__ import annotations

import json
import logging
import time
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text

from worker.db import SessionLocal
from worker.llm.openrouter import generate_with_schema
from worker.prompts import render
from worker.redis_helpers import add_spend
from worker.sanitize import sanitize_text


_log = logging.getLogger(__name__)
_ESTIMATED_COST_USD = 0.0002


class TranslationOutput(BaseModel):
    canonical_translated: str
    paraphrases_translated: list[str] = []
    examples_translated: list[str] = []


async def translate_definition(
    ctx: dict, definition_id: int, lang: str, job_id: str
) -> dict:
    """Translate a definition's canonical + paraphrases + examples to `lang`."""
    redis = ctx["redis"]
    job_uuid = UUID(job_id)
    started = time.time()

    async with SessionLocal() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT d.canonical_meaning, t.value AS term_value
                      FROM definitions d
                      JOIN terms t ON t.id = d.term_id
                     WHERE d.id = :id
                    """
                ),
                {"id": definition_id},
            )
        ).first()
        if row is None or row.canonical_meaning is None:
            await _publish_failed(redis, job_id, "definition_not_found")
            return {"status": "failed"}

        prompt = render(
            "translate.md",
            term_value=row.term_value,
            canonical_meaning=row.canonical_meaning,
            target_lang=lang,
        )
        try:
            output = await generate_with_schema(prompt, TranslationOutput)
        except Exception as exc:  # noqa: BLE001
            _log.exception("translate_failed")
            await _publish_failed(redis, job_id, str(exc)[:300])
            return {"status": "failed"}

        await add_spend(redis, _ESTIMATED_COST_USD)
        translated = sanitize_text(output.canonical_translated)
        await session.execute(
            text(
                """
                UPDATE definitions
                   SET translation = jsonb_set(
                         coalesce(translation, '{}'::jsonb),
                         ARRAY[:lang],
                         to_jsonb(:val::text)
                       )
                 WHERE id = :id
                """
            ),
            {"id": definition_id, "lang": lang, "val": translated},
        )
        await session.execute(
            text(
                "UPDATE jobs SET status='completed', "
                "result=CAST(:r AS jsonb), updated_at=NOW() WHERE id=:id"
            ),
            {"r": json.dumps({"translation": translated}), "id": job_uuid},
        )
        await session.commit()
        await redis.publish(
            f"results:def_{definition_id}",
            json.dumps({"status": "completed", "lang": lang, "translation": translated}),
        )
    return {"status": "completed", "elapsed_s": time.time() - started}


async def _publish_failed(redis, job_id: str, error: str) -> None:
    await redis.publish(
        f"results:job_{job_id}",
        json.dumps({"status": "failed", "error": error}),
    )
