"""Transactional task-registry state changes and outbox leasing."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.tasks.models import (
    AsyncCommandReceipt,
    AsyncTask,
    AsyncTaskDelivery,
    AsyncTaskEvent,
    AsyncTaskInterest,
    AsyncTaskOutbox,
    AsyncTaskStatus,
    OutboxStatus,
)

TASK_LEASE_SECONDS = 120
OUTBOX_LEASE_SECONDS = 30
OUTBOX_RETRY_DELAYS_SECONDS = (1, 5, 30, 120, 300)
_REUSABLE_TASK_STATUSES = (
    AsyncTaskStatus.QUEUED,
    AsyncTaskStatus.RUNNING,
    AsyncTaskStatus.SUCCEEDED,
)


@dataclass(frozen=True)
class TaskSubmission:
    task: AsyncTask
    interest: AsyncTaskInterest
    receipt: AsyncCommandReceipt
    task_created: bool


@dataclass(frozen=True)
class QuestionDeliverySubmission:
    task: AsyncTask
    delivery: AsyncTaskDelivery
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
    """
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
            result={"dispatch": dispatch} if dispatch is not None else None,
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


def _delivery_snapshot(task: AsyncTask, delivery: AsyncTaskDelivery) -> dict | None:
    """Select the private question variant without exposing the shared work key."""
    if task.status != AsyncTaskStatus.SUCCEEDED or not task.result:
        return None
    for question in task.result.get("questions", []):
        if (
            question.get("sense_id") == delivery.sense_id
            and question.get("format") == delivery.question_format
            and question.get("id") is not None
        ):
            return {
                "taskId": str(task.id),
                "questionId": question["id"],
                "senseId": delivery.sense_id,
                "format": delivery.question_format,
            }
    return None


async def submit_question_delivery(
    session: AsyncSession,
    *,
    server_work_key: str,
    owner_id: UUID,
    session_id: str,
    sense_id: int,
    question_format: str,
    command_id: str,
    dispatch: dict,
) -> QuestionDeliverySubmission:
    """Join shared question work and persist this session's private projection."""
    submission = await submit_or_join(
        session,
        kind="question_pool",
        server_work_key=server_work_key,
        requester_id=owner_id,
        command_kind="learning.question",
        command_id=command_id,
        provenance=f"session:{session_id}",
        dispatch=dispatch,
    )
    delivery = None
    if submission.receipt.delivery_id is not None:
        delivery = await session.get(AsyncTaskDelivery, submission.receipt.delivery_id)
    if delivery is None:
        delivery = await session.scalar(
            select(AsyncTaskDelivery).where(
                AsyncTaskDelivery.task_id == submission.task.id,
                AsyncTaskDelivery.session_id == session_id,
            )
        )
    if delivery is None:
        delivery = AsyncTaskDelivery(
            task_id=submission.task.id,
            session_id=session_id,
            owner_id=owner_id,
            sense_id=sense_id,
            question_format=question_format,
        )
        session.add(delivery)
        await session.flush()
    if delivery.snapshot is None:
        delivery.snapshot = _delivery_snapshot(submission.task, delivery)
        if delivery.snapshot is not None:
            delivery.resolved_at = _now()
    submission.receipt.delivery_id = delivery.id
    await session.commit()
    await session.refresh(delivery)
    return QuestionDeliverySubmission(submission.task, delivery, submission.task_created)


async def get_question_delivery(
    session: AsyncSession, delivery_id: UUID, *, session_id: str, owner_id: UUID
) -> AsyncTaskDelivery | None:
    """Return only the delivery authorized for its owning learning session."""
    return await session.scalar(
        select(AsyncTaskDelivery).where(
            AsyncTaskDelivery.id == delivery_id,
            AsyncTaskDelivery.session_id == session_id,
            AsyncTaskDelivery.owner_id == owner_id,
        )
    )


async def complete_question_task(
    session: AsyncSession,
    task_id: UUID,
    *,
    lease_token: str,
    lease_fence: int,
    result: dict,
) -> AsyncTask | None:
    """Atomically publish a shared result and resolve every private delivery."""
    task = await session.scalar(select(AsyncTask).where(AsyncTask.id == task_id).with_for_update())
    if (
        task is None
        or task.status != AsyncTaskStatus.RUNNING
        or task.lease_token != lease_token
        or task.lease_fence != lease_fence
    ):
        return None
    task.status = AsyncTaskStatus.SUCCEEDED
    task.result = result
    task.error_code = None
    task.lease_owner = task.lease_token = None
    task.lease_expires_at = None
    task.version += 1
    deliveries = list(
        (await session.execute(
            select(AsyncTaskDelivery)
            .where(AsyncTaskDelivery.task_id == task.id, AsyncTaskDelivery.snapshot.is_(None))
            .with_for_update()
        )).scalars()
    )
    for delivery in deliveries:
        delivery.snapshot = _delivery_snapshot(task, delivery)
        if delivery.snapshot is not None:
            delivery.resolved_at = _now()
    await _record_event_and_outbox(session, task)
    await session.commit()
    await session.refresh(task)
    return task


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
    return [task for task in tasks if task.result and isinstance(task.result.get("dispatch"), dict)]


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
        retry_index = min(max(task.attempt - 1, 0), len(OUTBOX_RETRY_DELAYS_SECONDS) - 1)
        task.next_attempt_at = _now() + timedelta(seconds=OUTBOX_RETRY_DELAYS_SECONDS[retry_index])
    task.version += 1
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
        retry_index = min(row.attempt - 1, len(OUTBOX_RETRY_DELAYS_SECONDS) - 1)
        row.status = OutboxStatus.PENDING
        row.next_attempt_at = _now() + timedelta(seconds=OUTBOX_RETRY_DELAYS_SECONDS[retry_index])
    await session.commit()
    await session.refresh(row)
    return row
