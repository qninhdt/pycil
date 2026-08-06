"""Owner-scoped assistant threads, recoverable SSE runs, and HITL decisions."""

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.assistant.application.hitl import (
    claim_decision,
    finish_action,
    mark_executing,
    validate_action_freshness,
)
from pycil.assistant.application.persistence import (
    create_or_load_run,
    require_owned_thread,
    retention_deadline,
    revalidate_actor,
)
from pycil.assistant.application.run_service import (
    acquire_lease,
    append_event,
    checkpoint_thread_id,
    checkpoint_version,
    set_run_status,
    stream_run,
)
from pycil.assistant.domain.context import AssistantContext
from pycil.assistant.domain.schemas import (
    ActionDecision,
    MessageCreate,
    RunEventRead,
    RunRead,
    RunRecoveryRead,
    ThreadCreate,
    ThreadRead,
)
from pycil.assistant.infra.models import (
    ActionStatus,
    AssistantAction,
    AssistantActionAudit,
    AssistantRun,
    AssistantRunEvent,
    AssistantThread,
    RunStatus,
)
from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    error_responses,
)
from pycil.config import settings
from pycil.db.redis import get_redis
from pycil.db.session import async_session_factory, get_session

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AssistantSSEEvent(BaseModel):
    """Named contract for one logical event encoded in the SSE response stream."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(description="Monotonically increasing event id for reconnection.")
    event: str = Field(description="Event type, such as token, action, error, or done.")
    data: dict = Field(description="Sanitized JSON event payload.")


SSE_RESPONSE = {
    200: {
        "model": AssistantSSEEvent,
        "description": "A recoverable server-sent event stream.",
        "content": {
            "text/event-stream": {
                "schema": {
                    "type": "string",
                    "description": "SSE frames; each data payload matches AssistantSSEEvent.",
                    "x-pycil-sse-event-schema": "#/components/schemas/AssistantSSEEvent",
                }
            }
        },
    }
}
SSE_OPENAPI_EXTENSION = {
    "x-pycil-sse-contract": {
        "eventSchema": "#/components/schemas/AssistantSSEEvent",
        "frame": "id: <sequence>\\nevent: <event>\\ndata: <json>\\n\\n",
        "reconnectHeader": "Last-Event-ID",
    }
}


def _event_frame(event: AssistantRunEvent) -> str:
    payload = json.dumps(event.sanitized_payload, separators=(",", ":"), default=str)
    return f"id: {event.sequence}\nevent: {event.event_type}\ndata: {payload}\n\n"


async def _persisted_events(run_id: UUID, after: int = 0) -> AsyncIterator[str]:
    async with async_session_factory() as session:
        events = await session.scalars(
            select(AssistantRunEvent)
            .where(AssistantRunEvent.run_id == run_id, AssistantRunEvent.sequence > after)
            .order_by(AssistantRunEvent.sequence)
        )
        for event in events:
            yield _event_frame(event)


def _graph(request: Request):
    graph = getattr(request.app.state, "assistant_graph", None)
    if graph is None:
        raise ServiceUnavailableError("assistant_not_configured", code="assistant_not_configured")
    return graph


def _stream(generator: AsyncIterator[str]) -> StreamingResponse:
    async def heartbeats() -> AsyncIterator[str]:
        iterator = generator.__aiter__()
        pending = asyncio.create_task(anext(iterator))
        try:
            while True:
                done, _ = await asyncio.wait({pending}, timeout=15)
                if not done:
                    yield ": heartbeat\n\n"
                    continue
                try:
                    yield pending.result()
                except StopAsyncIteration:
                    return
                pending = asyncio.create_task(anext(iterator))
        finally:
            pending.cancel()

    return StreamingResponse(
        heartbeats(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _last_event_id(request: Request) -> int:
    try:
        return max(0, int(request.headers.get("Last-Event-ID", "0")))
    except ValueError:
        return 0


@router.post("/threads", response_model=ThreadRead, status_code=201)
async def create_thread(
    body: ThreadCreate,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ThreadRead:
    thread = AssistantThread(
        owner_id=user.id, title=body.title, retention_deadline=retention_deadline()
    )
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return ThreadRead.model_validate(thread)


@router.get("/threads", response_model=list[ThreadRead])
async def list_threads(
    user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[ThreadRead]:
    rows = await session.scalars(
        select(AssistantThread)
        .where(AssistantThread.owner_id == user.id, AssistantThread.status == "active")
        .order_by(AssistantThread.updated_at.desc())
    )
    return [ThreadRead.model_validate(row) for row in rows]


@router.get("/threads/{thread_id}/messages", response_model=list[RunEventRead])
async def thread_messages(
    thread_id: UUID,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[RunEventRead]:
    thread = await require_owned_thread(session, thread_id, user.id)
    thread.retention_deadline = retention_deadline()
    await session.commit()
    events = await session.execute(
        select(AssistantRunEvent)
        .join(AssistantRun, AssistantRun.id == AssistantRunEvent.run_id)
        .where(AssistantRun.thread_id == thread_id)
        .order_by(AssistantRunEvent.created_at, AssistantRunEvent.sequence)
    )
    return [RunEventRead.model_validate(e) for e in events.scalars()]


@router.get("/threads/{thread_id}/runs/{run_id}", response_model=RunRecoveryRead)
async def get_run(
    thread_id: UUID,
    run_id: UUID,
    after: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    await require_owned_thread(session, thread_id, user.id)
    run = await session.get(AssistantRun, run_id)
    if run is None or run.thread_id != thread_id or run.owner_id != user.id:
        raise NotFoundError("assistant_run_not_found")
    events = await session.scalars(
        select(AssistantRunEvent)
        .where(AssistantRunEvent.run_id == run.id, AssistantRunEvent.sequence > after)
        .order_by(AssistantRunEvent.sequence)
    )
    # Returned as the model rather than a hand-dumped dict: `response_model` then
    # applies the aliases itself, so the camelCase output cannot drift from the
    # schema the way two separate `model_dump(by_alias=True)` calls could.
    return RunRecoveryRead(
        **RunRead.model_validate(run).model_dump(),
        events=[RunEventRead.model_validate(e) for e in events],
    )


@router.post(
    "/threads/{thread_id}/messages",
    response_class=StreamingResponse,
    responses={**SSE_RESPONSE, **error_responses(401, 404, 409, 422, 429, 503)},
    openapi_extra=SSE_OPENAPI_EXTENSION,
)
async def send_message(
    thread_id: UUID,
    body: MessageCreate,
    request: Request,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    if len(body.content) > settings.assistant_max_message_chars:
        raise ServiceUnavailableError(
            "assistant_message_too_long", code="assistant_message_too_long"
        )
    graph = _graph(request)
    thread = await require_owned_thread(session, thread_id, user.id)
    thread.retention_deadline = retention_deadline()
    await session.commit()
    run, created = await create_or_load_run(
        session, thread_id=thread_id, owner_id=user.id, client_message_id=body.client_message_id
    )
    lease_key = f"assistant:run:{user.id}:{thread_id}"
    retry_unstarted_run = (
        not created and run.status == RunStatus.PENDING and await get_redis().get(lease_key) is None
    )
    if not created and not retry_unstarted_run:
        return _stream(_persisted_events(run.id, _last_event_id(request)))
    if not await acquire_lease(user.id, thread_id, run.id):
        if created:
            await set_run_status(run.id, RunStatus.FAILED, "capacity_exhausted")
        raise ConflictError("assistant_capacity_exhausted")
    if created:
        await append_event(run.id, "user_message", {"content": body.content})

    async def events():
        async for event in stream_run(
            graph,
            run,
            AssistantContext(user.id, user.token_version),
            content=body.content,
            lease_acquired=True,
        ):
            yield _event_frame(event)

    return _stream(events())


@router.post(
    "/threads/{thread_id}/actions/{action_id}/confirm",
    response_class=StreamingResponse,
    responses={**SSE_RESPONSE, **error_responses(401, 404, 409, 422, 429, 503)},
    openapi_extra=SSE_OPENAPI_EXTENSION,
)
async def confirm_action(
    thread_id: UUID,
    action_id: UUID,
    body: ActionDecision,
    request: Request,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    await require_owned_thread(session, thread_id, user.id)
    await revalidate_actor(session, user.id, user.token_version)
    action = await claim_decision(session, action_id, user.id, body.decision)
    if body.decision == "approve":
        await validate_action_freshness(session, action)
    run = await session.get(AssistantRun, action.run_id)
    if run is None or run.thread_id != thread_id:
        raise NotFoundError("assistant_action_not_found")
    graph = _graph(request)
    if body.decision == "approve" and action.checkpoint_version not in {None, "unknown"}:
        config = {"configurable": {"thread_id": checkpoint_thread_id(user.id, thread_id)}}
        if await checkpoint_version(graph, config) != action.checkpoint_version:
            action.status = ActionStatus.INVALIDATED
            await session.commit()
            raise ServiceUnavailableError(
                "assistant_action_checkpoint_stale", code="assistant_action_stale"
            )
    if not await acquire_lease(user.id, thread_id, run.id):
        raise ConflictError("assistant_capacity_exhausted")

    async def events():
        succeeded = False
        if body.decision == "approve":
            # The transition happens only once the response body is consumed;
            # a client that never opens its stream cannot strand an action.
            async with async_session_factory() as action_session:
                fresh = await action_session.get(AssistantAction, action.id, with_for_update=True)
                if fresh is None:
                    raise NotFoundError("assistant_action_not_found")
                await mark_executing(action_session, fresh)
        try:
            async for event in stream_run(
                graph,
                run,
                AssistantContext(user.id, user.token_version, action.id),
                resume=body.decision,
                lease_acquired=True,
            ):
                succeeded = event.event_type == "done"
                yield _event_frame(event)
        finally:
            if body.decision == "approve":
                await finish_action(action.id, succeeded)

    return _stream(events())


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: UUID,
    request: Request,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    thread = await require_owned_thread(session, thread_id, user.id)
    checkpointer = getattr(request.app.state, "assistant_checkpointer", None)
    if checkpointer is not None:
        # Keep the owner-bound thread if checkpoint deletion fails so retry is possible.
        await checkpointer.adelete_thread(checkpoint_thread_id(user.id, thread_id))
    run_ids = select(AssistantRun.id).where(AssistantRun.thread_id == thread.id)
    action_ids = select(AssistantAction.id).where(AssistantAction.run_id.in_(run_ids))
    await session.execute(
        update(AssistantActionAudit)
        .where(AssistantActionAudit.action_id.in_(action_ids))
        .values(action_id=None)
    )
    await session.execute(delete(AssistantAction).where(AssistantAction.run_id.in_(run_ids)))
    await session.execute(delete(AssistantRunEvent).where(AssistantRunEvent.run_id.in_(run_ids)))
    await session.execute(delete(AssistantRun).where(AssistantRun.thread_id == thread.id))
    await session.delete(thread)
    await session.commit()
