"""arq worker entrypoint.

Run with: `arq worker.main.WorkerSettings`
"""
from __future__ import annotations

import logging
import time

from arq import cron
from arq.connections import RedisSettings

from worker.config import get_settings
from worker.jobs.generate_question import generate_question
from worker.jobs.generate_term import generate_term
from worker.jobs.grade_answer import grade_answer
from worker.jobs.prewarm_questions import prewarm_questions
from worker.jobs.translate_definition import translate_definition
from worker.jobs.tts_render import tts_render

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

# Refreshed every minute by the heartbeat cron; the admin health endpoint reads
# this key to report worker liveness (`worker_heartbeat_age_s`).
WORKER_HEARTBEAT_KEY = "worker:heartbeat"
_HEARTBEAT_TTL_SECONDS = 180


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def heartbeat(ctx: dict) -> None:
    """Write the current epoch seconds to the worker heartbeat key."""
    await ctx["redis"].set(
        WORKER_HEARTBEAT_KEY, str(time.time()), ex=_HEARTBEAT_TTL_SECONDS
    )


class WorkerSettings:
    functions = [generate_term, generate_question, grade_answer, prewarm_questions, translate_definition, tts_render]
    cron_jobs = [cron(heartbeat, second={0, 30}, run_at_startup=True)]
    redis_settings = _redis_settings()
    max_tries = 2
    job_timeout = 90  # seconds; matches phase-03 spec
    keep_result = 300


def main() -> None:
    """Allows `python -m worker.main` for stub mode parity. Prefer `arq` CLI."""
    print("[worker] use `arq worker.main.WorkerSettings` to run.")


if __name__ == "__main__":
    main()
