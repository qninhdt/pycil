"""arq worker entrypoint.

Run with: ``arq pycil_worker.main.WorkerSettings``

Startup embeds one Lexicon and exposes its reader and worker-engine capabilities
separately. Lexi owns all dictionary storage and generation; Pycil's worker only
orchestrates its own jobs.
"""

# Register every ORM model in SQLModel metadata before any job runs. The worker
# writes rows the API would have registered through its routers at application
# startup — the grading job's ReviewLog needs both `users` and `nodes`, and the
# task tables need `users`. A foreign key is not resolved when its model is
# imported but when the flush sorts tables, so a missing registration surfaces as
# a NoReferencedTableError on the first write rather than at import, and only for
# whichever job happens to run first on a cold worker.
import asyncio
from uuid import uuid4

import asyncpg
import pycil.db.models  # noqa: F401
from arq.connections import RedisSettings
from arq.cron import cron
from lexi_ai import Lexicon
from pycil.config import settings
from pycil.ports.lexi import LexiReader, LexiWorkerEngine
from pycil.ports.lexi_embedded import create_lexicon_reader
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pycil_worker.jobs.dispatch_task_outbox import dispatch_task_outbox
from pycil_worker.jobs.generate_question import prepare_questions, prepare_questions_task
from pycil_worker.jobs.generate_word import generate_word_task
from pycil_worker.jobs.grade_answer import grade_answer_task, grade_answer_v1
from pycil_worker.jobs.heartbeat import heartbeat
from pycil_worker.jobs.reconcile_assistant_retention import reconcile_assistant_retention
from pycil_worker.jobs.reconcile_async_tasks import reconcile_async_tasks
from pycil_worker.jobs.reconcile_expired_assistant_actions import (
    reconcile_expired_assistant_actions,
)
from pycil_worker.jobs.reconcile_pending_grades import reconcile_pending_grades
from pycil_worker.lexi_library import create_lexicon_worker_engine

_OUTBOX_NOTIFICATION_CHANNEL = "async_task_outbox"


def create_embedded_lexi_worker_engine() -> tuple[Lexicon, LexiReader, LexiWorkerEngine]:
    """Build one Lexicon with isolated read and provider-enabled capabilities."""
    lexicon = Lexicon.from_settings()
    return lexicon, create_lexicon_reader(lexicon), create_lexicon_worker_engine(lexicon)


async def close_embedded_lexicon(lexicon: Lexicon) -> None:
    """Release resources owned by an embedded Lexicon instance."""
    await lexicon.close()


def _asyncpg_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _drain_task_outbox(ctx: dict) -> None:
    lock = ctx["task_outbox_drain_lock"]
    if lock.locked():
        return
    async with lock:
        await dispatch_task_outbox(ctx)


async def _start_task_outbox_listener(ctx: dict) -> None:
    async def on_notification(_connection, _pid, _channel, _payload) -> None:
        await _drain_task_outbox(ctx)

    connection = await asyncpg.connect(_asyncpg_url(settings.db_url))
    await connection.add_listener(_OUTBOX_NOTIFICATION_CHANNEL, on_notification)
    ctx["task_outbox_listener"] = connection
    ctx["task_outbox_notification_callback"] = on_notification


async def on_startup(ctx: dict) -> None:
    ctx["worker_id"] = str(uuid4())
    lexicon, reader, worker_engine = create_embedded_lexi_worker_engine()
    ctx["lexicon"] = lexicon
    ctx["lexi_reader"] = reader
    ctx["lexi_engine"] = worker_engine
    engine = create_async_engine(settings.db_url, pool_pre_ping=True)
    ctx["engine"] = engine
    ctx["session_factory"] = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ctx["task_outbox_drain_lock"] = asyncio.Lock()
    await heartbeat(ctx)
    await _start_task_outbox_listener(ctx)
    # Register LISTEN before the initial sweep so a committed event cannot slip
    # between them and wait for the periodic recovery sweep.
    await _drain_task_outbox(ctx)
    await reconcile_async_tasks(ctx)


async def on_shutdown(ctx: dict) -> None:
    listener = ctx.get("task_outbox_listener")
    callback = ctx.get("task_outbox_notification_callback")
    if listener is not None:
        if callback is not None:
            await listener.remove_listener(_OUTBOX_NOTIFICATION_CHANNEL, callback)
        await listener.close()
    lexicon = ctx.get("lexicon")
    if lexicon is not None:
        await close_embedded_lexicon(lexicon)
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


class WorkerSettings:
    functions = [
        generate_word_task,
        prepare_questions,
        prepare_questions_task,
        grade_answer_v1,
        grade_answer_task,
        reconcile_pending_grades,
        reconcile_async_tasks,
        reconcile_expired_assistant_actions,
        reconcile_assistant_retention,
        heartbeat,
        dispatch_task_outbox,
    ]
    cron_jobs = [
        cron(reconcile_pending_grades, minute={0, 10, 20, 30, 40, 50}),
        cron(reconcile_async_tasks, minute=set(range(60))),
        cron(reconcile_expired_assistant_actions, minute={0, 10, 20, 30, 40, 50}),
        cron(reconcile_assistant_retention, hour={3}, minute={15}),
        cron(heartbeat, minute=set(range(60))),
        cron(dispatch_task_outbox, minute=set(range(60))),
    ]
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_tries = 2  # grade_answer is idempotent, so a single retry is safe
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
