"""tts_render arq job.

Calls Gemini Flash TTS, uploads MP3 to B2 at `tts/{def_id}/{lang}.mp3`,
caches signed URL in `definitions.tts_url` JSONB. Per phase 10 plan.

Stub: actual Gemini call is deferred — returns 503 until configured.
"""
from __future__ import annotations

import json
import os
import time

from sqlalchemy import text

from worker.db import SessionLocal


async def tts_render(
    ctx: dict, definition_id: int, lang: str, job_id: str
) -> dict:
    """Render TTS audio for a definition; persist signed URL in JSONB.

    v0.2 stub: requires GEMINI_TTS_KEY + B2 configuration. Without those
    envs the job fails with `tts_not_configured`. Wire-up of the actual
    Gemini call is deferred.
    """
    redis = ctx["redis"]
    started = time.time()

    if not os.getenv("GEMINI_TTS_KEY") or not os.getenv("B2_BUCKET"):
        await redis.publish(
            f"results:def_{definition_id}",
            json.dumps({"status": "failed", "error": "tts_not_configured"}),
        )
        return {"status": "failed"}

    async with SessionLocal() as session:
        row = (
            await session.execute(
                text(
                    "SELECT d.canonical_meaning, t.value AS term_value "
                    "FROM definitions d JOIN terms t ON t.id = d.term_id "
                    "WHERE d.id = :id"
                ),
                {"id": definition_id},
            )
        ).first()
        if row is None or row.canonical_meaning is None:
            await redis.publish(
                f"results:def_{definition_id}",
                json.dumps({"status": "failed", "error": "definition_not_found"}),
            )
            return {"status": "failed"}

        # NOTE: real Gemini Flash TTS call + B2 upload happens here in v0.3.
        # For v0.2 we mark as completed-without-audio and surface an error.
        await redis.publish(
            f"results:def_{definition_id}",
            json.dumps(
                {
                    "status": "failed",
                    "error": "tts_renderer_not_implemented_in_v02",
                    "elapsed_s": time.time() - started,
                }
            ),
        )
    return {"status": "failed", "reason": "renderer_stub"}
