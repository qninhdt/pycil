"""Transactional task-registry state changes and outbox leasing."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.retry import next_attempt_delay
from pycil.tasks.models import (
    AsyncCommandReceipt,
    AsyncTask,
    AsyncTaskEvent,
    AsyncTaskInterest,
    AsyncTaskOutbox,
    AsyncTaskStatus,
    OutboxStatus,
)

TASK_LEASE_SECONDS = 120
OUTBOX_LEASE_SECONDS = 30
# How long an interest authorizes its channel, measured from creation.
#
# Not a guess. A task's worst case is `max_attempts` (4) leases of
# TASK_LEASE_SECONDS each, plus the retry backoff between them, plus up to one
# minute per attempt waiting for the reconciler cron to notice an expired lease:
# 4*(120+60) + 1 + 5 + 30 = 756s. The window has to outlive that, or an interest
# lapses while its own task is still running. Doubled to 30 minutes so a slower
# dependency does not silently start denying live work.
#
# Both production callers previously omitted this, and `authorize_subscription`
# reads NULL as "never expires", which is how 103 of 103 interests on the live
# database ended up authorizing terminal tasks forever.
INTEREST_TTL_SECONDS = 1_800
# Retained after a task settles. Subscribing *is* the read — there is no REST route
# that returns a task — and the client persists only unsettled ids, so a tab closed
# when the task finished re-subscribes on its next mount to collect the outcome.
# Revoking on the terminal transition answers that with code 103, which the activity
# store records via `markStale` with no recovery path. This hands the result over,
# then lapses.
TERMINAL_GRACE_SECONDS = 900
_REUSABLE_TASK_STATUSES = (
    AsyncTaskStatus.QUEUED,
    AsyncTaskStatus.RUNNING,
    AsyncTaskStatus.SUCCEEDED,
)
_TERMINAL_TASK_STATUSES = (
    AsyncTaskStatus.SUCCEEDED,
    AsyncTaskStatus.FAILED,
    AsyncTaskStatus.EXPIRED,
)


@dataclass(frozen=True)
class TaskSubmission:
    task: AsyncTask
    interest: AsyncTaskInterest
    receipt: AsyncCommandReceipt
    task_created: bool


def _now() -> datetime:
    return datetime.now(UTC)


def task_snapshot(task: AsyncTask, event_id: UUID) -> dict:
    """Return the only payload that can leave the outbox for a generic task."""
    return {
        "schema": "async-task.v1",
        "eventId": str(event_id),
        "taskId": str(task.id),
        "kind": task.kind,
        "status": task.status.value,
        "version": task.version,
        # Queued tasks hold private worker dispatch arguments until completion;
        # never expose those through the subscriber-facing snapshot.
        "result": task.result if task.status == AsyncTaskStatus.SUCCEEDED else None,
        "errorCode": task.error_code,
    }


async def _record_event_and_outbox(session: AsyncSession, task: AsyncTask) -> AsyncTaskEvent:
    event_id = uuid4()
    snapshot = task_snapshot(task, event_id)
    event = AsyncTaskEvent(id=event_id, task_id=task.id, version=task.version, snapshot=snapshot)
    session.add(event)
    session.add(
        AsyncTaskOutbox(
            event_id=event_id,
            channel=f"async:{task.id}",
            payload=snapshot,
        )
    )
    # PostgreSQL delivers this only when the surrounding task transition commits.
    # The worker still sweeps periodically if a notification is lost.
    await session.execute(text("SELECT pg_notify('async_task_outbox', '')"))
    return event


async def _existing_interest(
    session: AsyncSession, task_id: UUID, requester_id: UUID, provenance: str
) -> AsyncTaskInterest | None:
    return await session.scalar(
        select(AsyncTaskInterest).where(
            AsyncTaskInterest.task_id == task_id,
            AsyncTaskInterest.requester_id == requester_id,
            AsyncTaskInterest.provenance == provenance,
        )
    )


async def submit_or_join(
    session: AsyncSession,
    *,
    kind: str,
    server_work_key: str,
    requester_id: UUID,
    command_kind: str,
    command_id: str,
    provenance: str,
    expires_at: datetime | None = None,
    max_attempts: int = 4,
    dispatch: dict | None = None,
) -> TaskSubmission:
    """Persist one command receipt, interest, and reusable task atomically.

    Callers must have already authorized the source and derived the work key;
    this intentionally accepts neither a client task ID nor an untrusted key.

    ``expires_at`` defaults to ``INTEREST_TTL_SECONDS`` from now rather than to
    None. A None expiry authorizes the channel forever, which is what both
    production callers were silently getting.
    """
    if expires_at is None:
        expires_at = _now() + timedelta(seconds=INTEREST_TTL_SECONDS)
    existing_receipt = await session.scalar(
        select(AsyncCommandReceipt).where(
            AsyncCommandReceipt.requester_id == requester_id,
            AsyncCommandReceipt.command_kind == command_kind,
            AsyncCommandReceipt.command_id == command_id,
        )
    )
    if existing_receipt is not None:
        task = await session.get(AsyncTask, existing_receipt.task_id)
        if task is None:  # database FK makes this corruption, not a user error
            raise RuntimeError("async_command_receipt_missing_task")
        interest = await _existing_interest(session, task.id, requester_id, provenance)
        if interest is None:
            interest = AsyncTaskInterest(
                task_id=task.id,
                requester_id=requester_id,
                provenance=provenance,
                expires_at=expires_at,
            )
            session.add(interest)
            await session.commit()
            await session.refresh(interest)
        return TaskSubmission(task, interest, existing_receipt, False)

    task = await session.scalar(
        select(AsyncTask).where(
            AsyncTask.kind == kind,
            AsyncTask.work_key == server_work_key,
            AsyncTask.status.in_(_REUSABLE_TASK_STATUSES),
        )
    )
    task_created = task is None
    if task is None:
        task = AsyncTask(
            kind=kind,
            work_key=server_work_key,
            max_attempts=max_attempts,
            dispatch=dispatch,
        )
        session.add(task)
        try:
            await session.flush()
        except IntegrityError:
            # Another submitter won the partial unique index race. Re-read the
            # reusable task in the same request, then attach this interest.
            await session.rollback()
            task = await session.scalar(
                select(AsyncTask).where(
                    AsyncTask.kind == kind,
                    AsyncTask.work_key == server_work_key,
                    AsyncTask.status.in_(_REUSABLE_TASK_STATUSES),
                )
            )
            if task is None:
                raise
            task_created = False
    if task_created:
        await _record_event_and_outbox(session, task)

    interest = await _existing_interest(session, task.id, requester_id, provenance)
    if interest is None:
        interest = AsyncTaskInterest(
            task_id=task.id,
            requester_id=requester_id,
            provenance=provenance,
            expires_at=expires_at,
        )
        session.add(interest)
    receipt = AsyncCommandReceipt(
        requester_id=requester_id,
        command_kind=command_kind,
        command_id=command_id,
        task_id=task.id,
    )
    session.add(receipt)
    try:
        await session.commit()
    except IntegrityError:
        # A command replay raced us. Its receipt is authoritative; avoid
        # returning a second task/interest identity to the browser.
        await session.rollback()
        return await submit_or_join(
            session,
            kind=kind,
            server_work_key=server_work_key,
            requester_id=requester_id,
            command_kind=command_kind,
            command_id=command_id,
            provenance=provenance,
            expires_at=expires_at,
            max_attempts=max_attempts,
            dispatch=dispatch,
        )
    await session.refresh(task)
    await session.refresh(interest)
    await session.refresh(receipt)
    return TaskSubmission(task, interest, receipt, task_created)


async def claim_task(
    session: AsyncSession,
    task_id: UUID,
    lease_owner: str,
    *,
    lease_seconds: int = TASK_LEASE_SECONDS,
) -> AsyncTask | None:
    now = _now()
    task = await session.scalar(select(AsyncTask).where(AsyncTask.id == task_id).with_for_update())
    if task is None:
        return None
    claimable = (
        task.status == AsyncTaskStatus.QUEUED
        and task.next_attempt_at is not None
        and task.next_attempt_at <= now
    ) or (
        task.status == AsyncTaskStatus.RUNNING
        and task.lease_expires_at is not None
        and task.lease_expires_at <= now
    )
    if not claimable:
        return None
    if task.attempt >= task.max_attempts:
        task.status = AsyncTaskStatus.FAILED
        task.error_code = "lease_expired"
        task.lease_owner = task.lease_token = None
        task.lease_expires_at = None
    else:
        task.status = AsyncTaskStatus.RUNNING
        task.attempt += 1
        task.lease_owner = lease_owner
        task.lease_token = str(uuid4())
        task.lease_fence += 1
        task.lease_expires_at = now + timedelta(seconds=lease_seconds)
    task.version += 1
    await _record_event_and_outbox(session, task)
    await session.commit()
    await session.refresh(task)
    return task if task.status == AsyncTaskStatus.RUNNING else None


async def find_live_task(
    session: AsyncSession, *, kind: str, work_key: str
) -> AsyncTask | None:
    """Find a non-terminal task by its server-derived work key.

    For settle paths that hold the domain identity but not the task id — the
    pending-grade reconciler re-enqueues by response id, so the task row it needs to
    converge can only be reached through the same work key that created it.
    """
    return await session.scalar(
        select(AsyncTask).where(
            AsyncTask.kind == kind,
            AsyncTask.work_key == work_key,
            AsyncTask.status.in_([AsyncTaskStatus.QUEUED, AsyncTaskStatus.RUNNING]),
        )
    )


async def list_reenqueueable_tasks(session: AsyncSession) -> list[AsyncTask]:
    """Return durable task rows whose ARQ execution may have been lost."""
    now = _now()
    tasks = list(
        (
            await session.execute(
                select(AsyncTask).where(
                    ((AsyncTask.status == AsyncTaskStatus.QUEUED)
                    & (AsyncTask.next_attempt_at <= now))
                    | (
                        (AsyncTask.status == AsyncTaskStatus.RUNNING)
                        & (AsyncTask.lease_expires_at <= now)
                    )
                )
            )
        ).scalars()
    )
    return [task for task in tasks if isinstance(task.dispatch, dict)]


async def _clamp_interests_to_grace(session: AsyncSession, task_id: UUID) -> None:
    """Shorten a settled task's interests to the grace window.

    Revoking outright is what the obvious fix does, and it destroys the result:
    subscribing *is* the read, the client persists only unsettled ids, so a tab
    that was closed when the task finished re-subscribes on its next mount and
    would be answered with code 103 — recorded by `markStale`, which has no
    recovery path.

    Only shortens, never extends: an interest already expiring sooner keeps its
    own deadline, so this cannot resurrect one that has lapsed.
    """
    deadline = _now() + timedelta(seconds=TERMINAL_GRACE_SECONDS)
    await session.execute(
        update(AsyncTaskInterest)
        .where(
            AsyncTaskInterest.task_id == task_id,
            AsyncTaskInterest.revoked_at.is_(None),
            or_(
                AsyncTaskInterest.expires_at.is_(None),
                AsyncTaskInterest.expires_at > deadline,
            ),
        )
        .values(expires_at=deadline)
    )


async def transition_task(
    session: AsyncSession,
    task_id: UUID,
    *,
    lease_token: str,
    lease_fence: int,
    status: AsyncTaskStatus,
    result: dict | None = None,
    error_code: str | None = None,
) -> AsyncTask | None:
    """Apply a fenced terminal/retry transition and persist its event/outbox."""
    task = await session.scalar(select(AsyncTask).where(AsyncTask.id == task_id).with_for_update())
    if (
        task is None
        or task.status != AsyncTaskStatus.RUNNING
        or task.lease_token != lease_token
        or task.lease_fence != lease_fence
    ):
        return None
    task.status = status
    task.result = result
    task.error_code = error_code
    task.lease_owner = task.lease_token = None
    task.lease_expires_at = None
    if status == AsyncTaskStatus.QUEUED:
        task.next_attempt_at = _now() + timedelta(
            seconds=next_attempt_delay(task.attempt)
        )
    task.version += 1
    if status in _TERMINAL_TASK_STATUSES:
        await _clamp_interests_to_grace(session, task_id)
    await _record_event_and_outbox(session, task)
    await session.commit()
    await session.refresh(task)
    return task


async def claim_outbox_batch(
    session: AsyncSession, lease_owner: str, *, limit: int = 100
) -> list[AsyncTaskOutbox]:
    now = _now()
    rows = list(
        (
            await session.execute(
                select(AsyncTaskOutbox)
                .where(
                    or_(
                        (AsyncTaskOutbox.status == OutboxStatus.PENDING)
                        & (AsyncTaskOutbox.next_attempt_at <= now),
                        (AsyncTaskOutbox.status == OutboxStatus.LEASED)
                        & (AsyncTaskOutbox.lease_expires_at <= now),
                    )
                )
                .order_by(AsyncTaskOutbox.next_attempt_at, AsyncTaskOutbox.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).scalars()
    )
    for row in rows:
        row.status = OutboxStatus.LEASED
        row.attempt += 1
        row.lease_owner = lease_owner
        row.lease_expires_at = now + timedelta(seconds=OUTBOX_LEASE_SECONDS)
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return rows


async def acknowledge_outbox(
    session: AsyncSession, outbox_id: UUID, lease_owner: str
) -> AsyncTaskOutbox | None:
    row = await session.scalar(
        select(AsyncTaskOutbox).where(AsyncTaskOutbox.id == outbox_id).with_for_update()
    )
    if row is None or row.status != OutboxStatus.LEASED or row.lease_owner != lease_owner:
        return None
    row.status = OutboxStatus.DELIVERED
    row.delivered_at = _now()
    row.lease_owner = None
    row.lease_expires_at = None
    await session.commit()
    await session.refresh(row)
    return row


async def retry_outbox(
    session: AsyncSession, outbox_id: UUID, lease_owner: str
) -> AsyncTaskOutbox | None:
    row = await session.scalar(
        select(AsyncTaskOutbox).where(AsyncTaskOutbox.id == outbox_id).with_for_update()
    )
    if row is None or row.status != OutboxStatus.LEASED or row.lease_owner != lease_owner:
        return None
    row.lease_owner = None
    row.lease_expires_at = None
    if row.attempt >= row.max_attempts:
        row.status = OutboxStatus.DEAD_LETTER
    else:
        row.status = OutboxStatus.PENDING
        # Previously `min(attempt - 1, len - 1)` with no lower clamp, so an attempt of
        # 0 indexed [-1] and waited the LONGEST delay (300s) instead of the shortest.
        row.next_attempt_at = _now() + timedelta(
            seconds=next_attempt_delay(row.attempt)
        )
    await session.commit()
    await session.refresh(row)
    return row
