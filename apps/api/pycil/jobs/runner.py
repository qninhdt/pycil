"""Best-effort content tasks; each run owns its resources and has a hard deadline."""

import asyncio
import logging

from lexi_ai import Lexicon
from redis.asyncio import Redis

from pycil.jobs.contracts import TASK_KIND_QUESTION_SUPPLY, TASK_KIND_WORD
from pycil.jobs.receipts import STATUS_DONE, STATUS_FAILED, STATUS_RUNNING, update_job_status
from pycil.lexicon.embedded import create_lexicon_reader
from pycil.platform.settings import settings
from pycil.worker.jobs.generate_question import prepare_questions
from pycil.worker.jobs.generate_word import generate_word
from pycil.worker.lexi_library import create_lexicon_worker_engine

logger = logging.getLogger(__name__)
JOB_TIMEOUT_SECONDS = 10 * 60


async def run_job(job_id: str, kind: str, payload: dict) -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    lexicon = None
    try:
        await update_job_status(redis, job_id, STATUS_RUNNING)
        async with asyncio.timeout(JOB_TIMEOUT_SECONDS):
            lexicon = Lexicon.from_settings()
            context = {
                "redis": redis,
                "lexi_reader": create_lexicon_reader(lexicon),
                "lexi_engine": create_lexicon_worker_engine(lexicon),
            }
            handler = {
                TASK_KIND_WORD: generate_word,
                TASK_KIND_QUESTION_SUPPLY: prepare_questions,
            }[kind]
            result = await handler(context, payload)
        await update_job_status(redis, job_id, STATUS_DONE, result=result)
    except Exception as exc:
        logger.exception("content_job_failed", extra={"kind": kind, "job_id": job_id})
        error = (
            "question_supply_unavailable"
            if str(exc) == "question_supply_unavailable"
            else "job_failed"
        )
        await update_job_status(redis, job_id, STATUS_FAILED, error=error)
    finally:
        if lexicon is not None:
            await lexicon.close()
        await redis.aclose()
