"""tts_render arq job.

Calls Gemini Flash TTS, uploads MP3 to B2 at `tts/{def_id}/{lang}.mp3`,
caches signed URL in `definitions.tts_url` JSONB. Per phase 10 plan.
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import time

from sqlalchemy import text

from worker.db import SessionLocal
from worker.jobs.lifecycle import commit_terminal, is_terminal
from worker.llm.gemini_tts import synthesize


_log = logging.getLogger(__name__)


async def tts_render(
    ctx: dict, definition_id: int, lang: str, job_id: str
) -> dict:
    """Render TTS audio for a definition; persist signed URL in JSONB."""
    redis = ctx["redis"]
    started = time.time()
    bucket = os.getenv("B2_BUCKET")

    async with SessionLocal() as gate:
        if await is_terminal(gate, job_id):
            return {"status": "duplicate"}

    if not bucket or not (os.getenv("GEMINI_TTS_KEY") or os.getenv("GOOGLE_TTS_KEY")):
        async with SessionLocal() as session:
            await commit_terminal(
                session, job_id=job_id, status="failed", error="tts_not_configured"
            )
        await redis.publish(
            f"results:def_{definition_id}",
            json.dumps({"status": "failed", "error": "tts_not_configured"}),
        )
        return {"status": "failed", "reason": "not_configured"}

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
            await commit_terminal(
                session, job_id=job_id, status="failed", error="definition_not_found"
            )
            await redis.publish(
                f"results:def_{definition_id}",
                json.dumps({"status": "failed", "error": "definition_not_found"}),
            )
            return {"status": "failed"}

        script = f"{row.term_value}. {row.canonical_meaning}"

        try:
            mp3_bytes = await synthesize(script, lang)
        except RuntimeError as exc:
            _log.warning("tts_synth_failed: %s", exc)
            try_n = int(ctx.get("job_try", 1) or 1)
            max_tries = int(ctx.get("max_tries", 1) or 1)
            if try_n >= max_tries:
                await commit_terminal(
                    session, job_id=job_id, status="failed", error=str(exc)
                )
                await redis.publish(
                    f"results:def_{definition_id}",
                    json.dumps({"status": "failed", "error": str(exc)}),
                )
            raise

        try:
            url = await _upload_and_sign(definition_id, lang, mp3_bytes)
        except Exception as exc:  # noqa: BLE001
            _log.exception("tts_upload_failed")
            try_n = int(ctx.get("job_try", 1) or 1)
            max_tries = int(ctx.get("max_tries", 1) or 1)
            if try_n >= max_tries:
                await commit_terminal(
                    session, job_id=job_id, status="failed", error="upload_failed"
                )
                await redis.publish(
                    f"results:def_{definition_id}",
                    json.dumps({"status": "failed", "error": "upload_failed"}),
                )
            raise

        await session.execute(
            text(
                """
                UPDATE definitions
                   SET tts_url = jsonb_set(
                         coalesce(tts_url, '{}'::jsonb),
                         ARRAY[:lang],
                         to_jsonb(:url::text)
                       )
                 WHERE id = :id
                """
            ),
            {"id": definition_id, "lang": lang, "url": url},
        )
        committed = await commit_terminal(
            session,
            job_id=job_id,
            status="completed",
            result={"lang": lang, "url": url},
        )
        if not committed:
            return {"status": "duplicate"}
        await redis.publish(
            f"results:def_{definition_id}",
            json.dumps({"status": "completed", "lang": lang, "url": url}),
        )
    return {"status": "completed", "elapsed_s": time.time() - started}


async def _upload_and_sign(definition_id: int, lang: str, audio: bytes) -> str:
    """Upload MP3 to B2; return signed download URL valid 7d."""
    bucket = os.getenv("B2_BUCKET", "")
    key = f"tts/{definition_id}/{lang}.mp3"
    client = _s3_client()
    await asyncio.to_thread(
        client.put_object,
        Bucket=bucket,
        Key=key,
        Body=audio,
        ContentType="audio/mpeg",
    )
    return await asyncio.to_thread(
        client.generate_presigned_url,
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=7 * 86400,
    )


@functools.lru_cache(maxsize=1)
def _s3_client():
    """Per-process boto3 client. Lazy so each forked arq worker creates
    its own — boto3 clients are not fork-safe."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=os.getenv("B2_ENDPOINT"),
        aws_access_key_id=os.getenv("B2_KEY_ID"),
        aws_secret_access_key=os.getenv("B2_APPLICATION_KEY"),
        config=Config(signature_version="s3v4"),
    )
