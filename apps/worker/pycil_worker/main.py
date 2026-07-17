"""arq worker entrypoint.

Run with: ``arq pycil_worker.main.WorkerSettings``

Startup builds the in-process LexiClient and runs ``lexicon.init()`` ONCE (lexi's
schema is idempotent). Generation is single-writer — it happens in the worker
only, never the API, so lexi's per-key dedup guard holds. Three jobs only.
"""

from arq.connections import RedisSettings
from arq.cron import cron
from pycil.config import settings
from pycil.content.lexi_inprocess import InProcessLexiClient, build_lexicon
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pycil_worker.jobs.generate_question import generate_question
from pycil_worker.jobs.generate_word import generate_word
from pycil_worker.jobs.grade_answer import grade_answer, grade_answer_v1
from pycil_worker.jobs.reconcile_assistant_retention import reconcile_assistant_retention
from pycil_worker.jobs.reconcile_expired_assistant_actions import (
    reconcile_expired_assistant_actions,
)
from pycil_worker.jobs.reconcile_pending_grades import reconcile_pending_grades


async def on_startup(ctx: dict) -> None:
    lexicon = build_lexicon()
    await lexicon.init()  # idempotent lexi schema create
    ctx["lexi_client"] = InProcessLexiClient(lexicon)
    engine = create_async_engine(settings.db_url, pool_pre_ping=True)
    ctx["engine"] = engine
    ctx["session_factory"] = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def on_shutdown(ctx: dict) -> None:
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
        reconcile_expired_assistant_actions,
        reconcile_assistant_retention,
    ]
    cron_jobs = [
        cron(reconcile_pending_grades, minute={0, 10, 20, 30, 40, 50}),
        cron(reconcile_expired_assistant_actions, minute={0, 10, 20, 30, 40, 50}),
        cron(reconcile_assistant_retention, hour={3}, minute={15}),
    ]
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_tries = 2  # grade_answer is idempotent, so a single retry is safe
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
