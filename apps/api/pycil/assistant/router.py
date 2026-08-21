"""Owner-scoped assistant threads, recoverable SSE runs, and HITL decisions.

Routes own dependency wiring, authentication, and SSE framing; every state
transition lives in the application layer (`persistence`, `run_service`,
`message_flow`, `thread_lifecycle`, `hitl`).
"""

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.assistant.application import thread_lifecycle
from pycil.assistant.application.hitl import (
    claim_decision,
    require_action_run,
    validate_action_freshness,
)
from pycil.assistant.application.message_flow import (
    ensure_action_checkpoint_fresh,
    start_message_run,
    stream_resumed_run,
)
from pycil.assistant.application.persistence import (
    refresh_retention,
    require_owned_run,
    require_owned_thread,
    revalidate_actor,
    run_events,
    thread_events,
)
from pycil.assistant.application.run_service import acquire_lease, persisted_events, stream_run
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
from pycil.assistant.infra.models import AssistantRunEvent
from pycil.assistant.sse import SSE_OPENAPI_EXTENSION, SSE_RESPONSE
from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import (
    ConflictError,
    PayloadTooLargeError,
    ServiceUnavailableError,
    error_responses,
)
from pycil.config import settings
from pycil.db.session import get_session

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _event_frame(event: AssistantRunEvent) -> str:
    payload = json.dumps(event.sanitized_payload, separators=(",", ":"), default=str)
    return f"id: {event.sequence}\nevent: {event.event_type}\ndata: {payload}\n\n"


async def _framed(events: AsyncIterator[AssistantRunEvent]) -> AsyncIterator[str]:
    """Encode persisted event rows as SSE frames."""
    async for event in events:
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
    thread = await thread_lifecycle.create_thread(session, owner_id=user.id, title=body.title)
    return ThreadRead.model_validate(thread)


@router.get("/threads", response_model=list[ThreadRead])
async def list_threads(
    user: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[ThreadRead]:
    rows = await thread_lifecycle.list_active_threads(session, owner_id=user.id)
    return [ThreadRead.model_validate(row) for row in rows]


@router.get("/threads/{thread_id}/messages", response_model=list[RunEventRead])
async def thread_messages(
    thread_id: UUID,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[RunEventRead]:
    thread = await require_owned_thread(session, thread_id, user.id)
    await refresh_retention(session, thread)
    return [RunEventRead.model_validate(e) for e in await thread_events(session, thread_id)]


@router.get("/threads/{thread_id}/runs/{run_id}", response_model=RunRecoveryRead)
async def get_run(
    thread_id: UUID,
    run_id: UUID,
    after: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    await require_owned_thread(session, thread_id, user.id)
    run = await require_owned_run(session, run_id=run_id, thread_id=thread_id, owner_id=user.id)
    events = await run_events(session, run.id, after)
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
    responses={**SSE_RESPONSE, **error_responses(401, 404, 409, 413, 422, 429, 503)},
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
        # A client-side payload problem is a 4xx, not a server outage.
        raise PayloadTooLargeError("assistant_message_too_long")
    graph = _graph(request)
    started = await start_message_run(
        session,
        thread_id=thread_id,
        owner_id=user.id,
        client_message_id=body.client_message_id,
        content=body.content,
    )
    if started.replay_only:
        return _stream(_framed(persisted_events(started.run.id, _last_event_id(request))))
    context = AssistantContext(user.id, user.token_version)
    events = stream_run(graph, started.run, context, content=body.content, lease_acquired=True)
    return _stream(_framed(events))


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
    run = await require_action_run(session, action, thread_id)
    graph = _graph(request)
    if body.decision == "approve":
        await ensure_action_checkpoint_fresh(session, graph, user.id, thread_id, action)
    if not await acquire_lease(user.id, thread_id, run.id):
        raise ConflictError("assistant_capacity_exhausted")
    context = AssistantContext(user.id, user.token_version, action.id)
    events = stream_resumed_run(graph, run, context, resume=body.decision, action_id=action.id)
    return _stream(_framed(events))


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: UUID,
    request: Request,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    thread = await require_owned_thread(session, thread_id, user.id)
    checkpointer = getattr(request.app.state, "assistant_checkpointer", None)
    await thread_lifecycle.delete_thread(session, thread, checkpointer)
