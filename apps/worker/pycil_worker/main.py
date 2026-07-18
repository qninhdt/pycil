"""arq worker entrypoint.

Run with: ``arq pycil_worker.main.WorkerSettings``

Startup builds the authenticated Lexi HTTP client. Lexi owns all dictionary
storage and generation; Pycil's worker only orchestrates its own jobs.
"""

# Register the referenced users table in SQLModel metadata.  The worker writes
# WordGeneration records directly, while the API normally imports this model
# through its auth router during application startup.
import pycil.auth.models  # noqa: F401
from arq.connections import RedisSettings
from arq.cron import cron
from pycil.config import settings
from pycil.content.lexi_http import LexiHttpClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pycil_worker.jobs.generate_question import generate_question
from pycil_worker.jobs.generate_word import generate_word
from pycil_worker.jobs.grade_answer import grade_answer, grade_answer_v1
from pycil_worker.jobs.heartbeat import heartbeat
from pycil_worker.jobs.reconcile_assistant_retention import reconcile_assistant_retention
from pycil_worker.jobs.reconcile_expired_assistant_actions import (
    reconcile_expired_assistant_actions,
)
from pycil_worker.jobs.reconcile_pending_grades import reconcile_pending_grades
from pycil_worker.jobs.reconcile_queued_word_generations import reconcile_queued_word_generations


async def on_startup(ctx: dict) -> None:
    ctx["lexi_client"] = LexiHttpClient(
        settings.lexi_service_url,
        settings.lexi_service_token,
        settings.lexi_reference_dataset_fingerprint,
        timeout_seconds=settings.lexi_service_timeout_seconds,
        generation_timeout_seconds=settings.lexi_generation_timeout_seconds,
    )
    engine = create_async_engine(settings.db_url, pool_pre_ping=True)
    ctx["engine"] = engine
    ctx["session_factory"] = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await heartbeat(ctx)


async def on_shutdown(ctx: dict) -> None:
    client = ctx.get("lexi_client")
    if client is not None:
        await client.close()
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


class WorkerSettings:
    # Keep the legacy handler for already-enqueued jobs while producers use v1.
    functions = [
        generate_word,
        generate_question,
        grade_answer,
        grade_answer_v1,
        reconcile_pending_grades,
        reconcile_queued_word_generations,
        reconcile_expired_assistant_actions,
        reconcile_assistant_retention,
        heartbeat,
    ]
    cron_jobs = [
        cron(reconcile_pending_grades, minute={0, 10, 20, 30, 40, 50}),
        cron(reconcile_queued_word_generations, minute={1, 11, 21, 31, 41, 51}),
        cron(reconcile_expired_assistant_actions, minute={0, 10, 20, 30, 40, 50}),
        cron(reconcile_assistant_retention, hour={3}, minute={15}),
        cron(heartbeat, minute=set(range(60))),
    ]
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_tries = 2  # grade_answer is idempotent, so a single retry is safe
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
