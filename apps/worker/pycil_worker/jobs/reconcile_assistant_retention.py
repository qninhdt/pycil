"""Purge expired private assistant data while retaining policy-required audits."""

from datetime import UTC, datetime, timedelta

from psycopg import AsyncConnection
from pycil.assistant.models import (
    AssistantAction,
    AssistantActionAudit,
    AssistantRun,
    AssistantRunEvent,
    AssistantThread,
)
from pycil.config import settings
from sqlalchemy import delete, select, update


async def reconcile_assistant_retention(ctx: dict) -> int:
    """Delete inactive conversations/runs/events/actions and age out audits after 90 days."""
    async with ctx["session_factory"]() as session:
        threads = list(
            await session.scalars(
                select(AssistantThread).where(
                    AssistantThread.retention_deadline <= datetime.now(UTC)
                )
            )
        )
        checkpoint_thread_ids = [f"assistant:{thread.owner_id}:{thread.id}" for thread in threads]
        if checkpoint_thread_ids:
            async with await AsyncConnection.connect(
                settings.assistant_psycopg_url, autocommit=True
            ) as conn:
                async with conn.cursor() as cursor:
                    for checkpoint_thread_id in checkpoint_thread_ids:
                        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                            await cursor.execute(
                                f"DELETE FROM {table} WHERE thread_id = %s",
                                (checkpoint_thread_id,),
                            )
        for thread in threads:
            run_ids = select(AssistantRun.id).where(AssistantRun.thread_id == thread.id)
            action_ids = select(AssistantAction.id).where(AssistantAction.run_id.in_(run_ids))
            await session.execute(
                update(AssistantActionAudit)
                .where(AssistantActionAudit.action_id.in_(action_ids))
                .values(action_id=None)
            )
            await session.execute(
                delete(AssistantAction).where(AssistantAction.run_id.in_(run_ids))
            )
            await session.execute(
                delete(AssistantRunEvent).where(AssistantRunEvent.run_id.in_(run_ids))
            )
            await session.execute(delete(AssistantRun).where(AssistantRun.thread_id == thread.id))
            await session.delete(thread)
        audit_deadline = datetime.now(UTC) - timedelta(days=settings.assistant_audit_retention_days)
        await session.execute(
            delete(AssistantActionAudit).where(AssistantActionAudit.occurred_at < audit_deadline)
        )
        await session.commit()
    return len(threads)
