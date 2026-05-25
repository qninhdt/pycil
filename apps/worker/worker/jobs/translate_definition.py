"""translate_definition arq job.

Reads a definition, calls OpenRouter with the translate prompt for the
target language, persists result into `definitions.translation` JSONB
keyed by lang code, publishes terminal SSE frame.
"""
from __future__ import annotations

import json
import logging
import time

from pydantic import BaseModel
from sqlalchemy import text

from worker.db import SessionLocal
from worker.jobs.lifecycle import commit_terminal, is_terminal
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
    started = time.time()

    async with SessionLocal() as gate:
        if await is_terminal(gate, job_id):
            return {"status": "duplicate"}

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
            await commit_terminal(
                session, job_id=job_id, status="failed", error="definition_not_found"
            )
            await redis.publish(
                f"results:def_{definition_id}",
                json.dumps({"status": "failed", "error": "definition_not_found"}),
            )
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
            try_n = int(ctx.get("job_try", 1) or 1)
            max_tries = int(ctx.get("max_tries", 1) or 1)
            if try_n >= max_tries:
                await commit_terminal(
                    session, job_id=job_id, status="failed", error=str(exc)[:300]
                )
                await redis.publish(
                    f"results:def_{definition_id}",
                    json.dumps({"status": "failed", "error": str(exc)[:300]}),
                )
            raise

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
        committed = await commit_terminal(
            session,
            job_id=job_id,
            status="completed",
            result={"translation": translated},
        )
        if not committed:
            return {"status": "duplicate"}
        await redis.publish(
            f"results:def_{definition_id}",
            json.dumps({"status": "completed", "lang": lang, "translation": translated}),
        )
    return {"status": "completed", "elapsed_s": time.time() - started}
