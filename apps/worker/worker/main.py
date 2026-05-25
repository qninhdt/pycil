"""arq worker entrypoint.

Run with: `arq worker.main.WorkerSettings`
"""
from __future__ import annotations

import logging

from arq.connections import RedisSettings

from worker.config import get_settings
from worker.jobs.generate_question import generate_question
from worker.jobs.generate_term import generate_term
from worker.jobs.translate_definition import translate_definition
from worker.jobs.tts_render import tts_render

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    functions = [generate_term, generate_question, translate_definition, tts_render]
    redis_settings = _redis_settings()
    max_tries = 2
    job_timeout = 90  # seconds; matches phase-03 spec
    keep_result = 300


def main() -> None:
    """Allows `python -m worker.main` for stub mode parity. Prefer `arq` CLI."""
    print("[worker] use `arq worker.main.WorkerSettings` to run.")


if __name__ == "__main__":
    main()
