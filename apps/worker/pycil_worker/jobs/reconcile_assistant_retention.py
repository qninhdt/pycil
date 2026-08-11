"""Purge expired private assistant data while retaining policy-required audits."""

from datetime import UTC, datetime, timedelta

from psycopg import AsyncConnection
from pycil.assistant.infra.models import AssistantActionAudit, AssistantThread
from pycil.config import settings
from sqlalchemy import delete, select

from pycil_worker.context import ReadyWorkerContext

# LangGraph owns these and keys them by a `thread_id` string, not a foreign key, so
# no database cascade reaches them. Written out as literals rather than interpolated
# from a table list: the values were always parameterized, but a scanner cannot tell
# that from an f-string, and psycopg's own typing wants a LiteralString here.
_CHECKPOINT_DELETES = (
    "DELETE FROM checkpoint_writes WHERE thread_id = %s",
    "DELETE FROM checkpoint_blobs WHERE thread_id = %s",
    "DELETE FROM checkpoints WHERE thread_id = %s",
)


async def reconcile_assistant_retention(ctx: ReadyWorkerContext) -> int:
    """Delete inactive conversations/runs/events/actions and age out audits after 90 days.

    Runs, their events and their actions cascade from the thread (migration 0024), so
    only the root is deleted here. `assistant_action_audit.action_id` is SET NULL
    rather than CASCADE, which is what preserves the audit trail — that used to be a
    hand-written UPDATE, and it was the only thing standing between a policy-required
    record and deletion.
    """
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
                        for statement in _CHECKPOINT_DELETES:
                            await cursor.execute(statement, (checkpoint_thread_id,))
        for thread in threads:
            await session.delete(thread)
        audit_deadline = datetime.now(UTC) - timedelta(days=settings.assistant_audit_retention_days)
        await session.execute(
            delete(AssistantActionAudit).where(AssistantActionAudit.occurred_at < audit_deadline)
        )
        await session.commit()
    return len(threads)
