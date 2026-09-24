"""Purge expired assistant threads using the public checkpointer API."""

from datetime import UTC, datetime

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from pycil.assistant.infra.models import AssistantThread
from pycil.config import settings
from sqlalchemy import select

from pycil_worker.context import ReadyWorkerContext


async def reconcile_assistant_retention(ctx: ReadyWorkerContext) -> int:
    """Delete threads whose retained history has expired.

    The deadline alone decides. A conversation still in use has a fresh deadline
    because the API refreshes it whenever the thread is opened, so a thread
    cannot expire while a learner is reading it. There is no separate "active
    turn" column to consult: an in-flight turn is bounded by the Redis lease,
    which outlives the turn but not the retention window.
    """
    async with ctx["session_factory"]() as session:
        threads = list(
            await session.scalars(
                select(AssistantThread)
                .where(AssistantThread.retention_deadline <= datetime.now(UTC))
                .with_for_update(skip_locked=True)
            )
        )
        if threads:
            async with await AsyncConnection.connect(
                settings.assistant_psycopg_url, autocommit=True
            ) as connection:
                checkpointer = AsyncPostgresSaver(connection)
                for thread in threads:
                    await checkpointer.adelete_thread(f"assistant:{thread.owner_id}:{thread.id}")
                    await session.delete(thread)
        await session.commit()
    return len(threads)
