"""Generic task registry invariants before any producer switches to it."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from pycil.auth.models import User
from pycil.tasks import service
from pycil.tasks.models import (
    AsyncTaskEvent,
    AsyncTaskOutbox,
    AsyncTaskStatus,
    OutboxStatus,
)

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_same_work_joins_one_task_with_separate_interests_and_receipts(session):
    first_user = await _user(session, "first-task-interest@example.com")
    second_user = await _user(session, "second-task-interest@example.com")
    kwargs = {
        "kind": "word",
        "server_work_key": "word:example:dataset-v1",
        "command_kind": "word.generate",
        "provenance": "word-search",
    }

    first = await service.submit_or_join(
        session, requester_id=first_user.id, command_id="first-command", **kwargs
    )
    joined = await service.submit_or_join(
        session, requester_id=second_user.id, command_id="second-command", **kwargs
    )
    replay = await service.submit_or_join(
        session, requester_id=first_user.id, command_id="first-command", **kwargs
    )

    assert first.task_created
    assert not joined.task_created
    assert joined.task.id == first.task.id == replay.task.id
    assert first.interest.requester_id != joined.interest.requester_id
    assert replay.receipt.id == first.receipt.id
    events = (await session.execute(select(AsyncTaskEvent))).scalars().all()
    outbox = (await session.execute(select(AsyncTaskOutbox))).scalars().all()
    assert len(events) == len(outbox) == 1
    assert events[0].snapshot["schema"] == "async-task.v1"
    assert events[0].snapshot["taskId"] == str(first.task.id)
    assert events[0].snapshot["version"] == 1
    assert first.task.work_key not in events[0].snapshot.values()


async def test_queued_dispatch_payload_is_private_and_recoverable(session):
    user = await _user(session, "task-dispatch@example.com")
    submission = await service.submit_or_join(
        session,
        kind="word",
        server_work_key="word:dispatch:dataset-v1",
        requester_id=user.id,
        command_kind="word.generate",
        command_id="dispatch-command",
        provenance="word-search",
        dispatch={"query": "run"},
    )

    event = await session.scalar(
        select(AsyncTaskEvent).where(AsyncTaskEvent.task_id == submission.task.id)
    )
    recoverable = await service.list_reenqueueable_tasks(session)

    assert event is not None and event.snapshot["result"] is None
    assert recoverable == [submission.task]
    assert recoverable[0].result == {"dispatch": {"query": "run"}}


async def test_fenced_transition_writes_one_versioned_event_and_outbox(session):
    user = await _user(session, "task-fence@example.com")
    submission = await service.submit_or_join(
        session,
        kind="grading",
        server_work_key="grading:response-id",
        requester_id=user.id,
        command_kind="grading.submit",
        command_id="grade-command",
        provenance="response-owner",
    )
    claimed = await service.claim_task(session, submission.task.id, "worker-a", lease_seconds=0)
    assert claimed is not None
    stale_token, stale_fence = claimed.lease_token, claimed.lease_fence
    reclaimed = await service.claim_task(session, submission.task.id, "worker-b")
    assert reclaimed is not None
    assert reclaimed.lease_fence == stale_fence + 1

    assert (
        await service.transition_task(
            session,
            submission.task.id,
            lease_token=stale_token,
            lease_fence=stale_fence,
            status=AsyncTaskStatus.SUCCEEDED,
            result={"responseId": "response-id"},
        )
        is None
    )
    completed = await service.transition_task(
        session,
        submission.task.id,
        lease_token=reclaimed.lease_token,
        lease_fence=reclaimed.lease_fence,
        status=AsyncTaskStatus.SUCCEEDED,
        result={"responseId": "response-id"},
    )
    assert completed is not None and completed.version == 4

    events = (
        await session.execute(
            select(AsyncTaskEvent).where(AsyncTaskEvent.task_id == submission.task.id)
        )
    ).scalars().all()
    assert [event.version for event in events] == [1, 2, 3, 4]
    assert all(event.snapshot["eventId"] for event in events)


async def test_outbox_retry_preserves_event_identity_until_acknowledged(session):
    user = await _user(session, "outbox@example.com")
    await service.submit_or_join(
        session,
        kind="word",
        server_work_key="word:outbox:dataset-v1",
        requester_id=user.id,
        command_kind="word.generate",
        command_id="outbox-command",
        provenance="word-search",
    )
    leased = await service.claim_outbox_batch(session, "relay-a")
    assert len(leased) == 1 and leased[0].status == OutboxStatus.LEASED
    event_id = leased[0].payload["eventId"]

    retried = await service.retry_outbox(session, leased[0].id, "relay-a")
    assert retried is not None and retried.status == OutboxStatus.PENDING
    retried.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()
    leased_again = await service.claim_outbox_batch(session, "relay-b")
    assert leased_again[0].payload["eventId"] == event_id
    acknowledged = await service.acknowledge_outbox(session, leased_again[0].id, "relay-b")
    assert acknowledged is not None and acknowledged.status == OutboxStatus.DELIVERED
