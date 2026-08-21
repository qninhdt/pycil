"""How an HTTP turn becomes a run: start, replay, or resume.

The router authenticates and frames SSE; this module decides what a request does
to run state. A submitted message either creates and executes a new run, retries
a PENDING run whose lease lapsed before it started, or replays an existing run's
persisted events. A confirmation resumes an interrupted run and carries the
approved action's terminal transition with it.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pycil.assistant.application.hitl import begin_action_execution, finish_action
from pycil.assistant.application.persistence import (
    create_or_load_run,
    refresh_retention,
    require_owned_thread,
)
from pycil.assistant.application.run_service import (
    acquire_lease,
    append_event,
    checkpoint_thread_id,
    checkpoint_version,
    lease_held,
    set_run_status,
    stream_run,
)
from pycil.assistant.domain.context import AssistantContext
from pycil.assistant.infra.models import ActionStatus, AssistantAction, AssistantRun, RunStatus
from pycil.common.errors import ConflictError, ServiceUnavailableError


@dataclass(frozen=True)
class StartedMessageRun:
    """What a submitted message should do: execute ``run``, or replay its events."""

    run: AssistantRun
    replay_only: bool


async def start_message_run(
    session: AsyncSession,
    *,
    thread_id: UUID,
    owner_id: UUID,
    client_message_id: UUID,
    content: str,
) -> StartedMessageRun:
    """Resolve a submitted message to execute-or-replay, committing run state.

    A run still PENDING whose lease has lapsed never started executing; the retry
    of its ``client_message_id`` must re-execute it (without duplicating the
    user_message event) rather than replay an empty stream.
    """
    thread = await require_owned_thread(session, thread_id, owner_id)
    await refresh_retention(session, thread)
    run, created = await create_or_load_run(
        session, thread_id=thread_id, owner_id=owner_id, client_message_id=client_message_id
    )
    if created:
        if not await acquire_lease(owner_id, thread_id, run.id):
            await set_run_status(run.id, RunStatus.FAILED, "capacity_exhausted")
            raise ConflictError("assistant_capacity_exhausted")
        await append_event(run.id, "user_message", {"content": content})
        return StartedMessageRun(run=run, replay_only=False)
    if run.status == RunStatus.PENDING and not await lease_held(owner_id, thread_id):
        # The failed attempt never marked the run FAILED, so capacity rejection
        # here must not either: the run simply stays available for another try.
        if not await acquire_lease(owner_id, thread_id, run.id):
            raise ConflictError("assistant_capacity_exhausted")
        return StartedMessageRun(run=run, replay_only=False)
    return StartedMessageRun(run=run, replay_only=True)


async def ensure_action_checkpoint_fresh(
    session: AsyncSession,
    graph,
    owner_id: UUID,
    thread_id: UUID,
    action: AssistantAction,
) -> None:
    """Reject an approval whose checkpoint was superseded since the proposal.

    Executing against a different checkpoint would apply a decision to graph
    state the learner never saw. The action is invalidated rather than left
    pending so no later approval can revive it.
    """
    if action.checkpoint_version in {None, "unknown"}:
        return
    config = {"configurable": {"thread_id": checkpoint_thread_id(owner_id, thread_id)}}
    if await checkpoint_version(graph, config) == action.checkpoint_version:
        return
    action.status = ActionStatus.INVALIDATED
    await session.commit()
    raise ServiceUnavailableError(
        "assistant_action_checkpoint_stale", code="assistant_action_stale"
    )


async def stream_resumed_run(
    graph,
    run: AssistantRun,
    context: AssistantContext,
    *,
    resume: str,
    action_id: UUID,
):
    """Resume a run under a held lease, finalizing an approved action with the outcome."""
    succeeded = False
    if resume == "approve":
        await begin_action_execution(action_id)
    try:
        async for event in stream_run(graph, run, context, resume=resume, lease_acquired=True):
            succeeded = event.event_type == "done"
            yield event
    finally:
        if resume == "approve":
            await finish_action(action_id, succeeded)
