"""Owner-scoped assistant threads and the AG-UI run endpoint.

The AG-UI protocol is served by the maintained ``ag-ui-langgraph`` adapter, which
owns the event stream. What this module adds is everything the adapter cannot know
about Pycil: which learner owns a thread, which model they may run, how one active
turn is enforced, and how a turn is charged.

Ownership is checked here, before the adapter runs, because the adapter takes the
checkpoint key from the request. A client-supplied thread id is a *request* to
read that conversation, not an authorization to read it.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from ag_ui.core import RunAgentInput, RunErrorEvent
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account import credit
from pycil.assistant.application import thread_lifecycle
from pycil.assistant.application.ag_ui_agent import checkpoint_thread_id
from pycil.assistant.application.attachments import AttachmentRejected, validate_attachments
from pycil.assistant.application.middleware import log_turn_usage
from pycil.assistant.application.persistence import (
    refresh_retention,
    require_owned_thread,
    revalidate_actor,
)
from pycil.assistant.application.turn_lease import (
    acquire_turn_lease,
    lease_ttl_seconds,
    pending_lease_ttl_seconds,
    release_turn_lease,
    renew_turn_lease,
)
from pycil.assistant.domain.context import AssistantContext
from pycil.assistant.domain.schemas import (
    MessageCreate,
    ModelCatalogRead,
    ResumeDecision,
    ThreadCreate,
    ThreadRead,
    ThreadStateRead,
)
from pycil.assistant.domain.usage import TurnUsage
from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import (
    ConflictError,
    PayloadTooLargeError,
    ServiceUnavailableError,
    error_responses,
)
from pycil.config import settings
from pycil.db.redis import get_redis
from pycil.db.session import get_session, session_scope
from pycil.product_config import system_config

logger = logging.getLogger(__name__)
_USAGE_PENDING_TTL_SECONDS = max(1, settings.assistant_retention_days) * 24 * 60 * 60

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _agent(request: Request):
    agent = getattr(request.app.state, "assistant_agent", None)
    if agent is None:
        raise ServiceUnavailableError("assistant_not_configured", code="assistant_not_configured")
    return agent


def _graph(request: Request):
    graph = getattr(request.app.state, "assistant_graph", None)
    if graph is None:
        raise ServiceUnavailableError("assistant_not_configured", code="assistant_not_configured")
    return graph


def _selection(body: RunAgentInput) -> tuple[str | None, str | None]:
    """The model and reasoning effort a client asked for, if any.

    Read from ``forwarded_props`` because that is the field the AG-UI client
    already uses for per-run options. It is a request: the server validates it
    against the catalog and prices the turn from its own copy of the tariff.
    """
    props = body.forwarded_props or {}
    if not isinstance(props, dict):
        return None, None
    model_id = props.get("model") or props.get("modelId")
    effort = props.get("reasoningEffort") or props.get("reasoning_effort")
    return (
        model_id if isinstance(model_id, str) else None,
        effort if isinstance(effort, str) else None,
    )


def _run_reference(owner_id: UUID, thread_id: UUID, run_id: str) -> UUID:
    """Stable server-side ledger key for an AG-UI run and every resume request."""
    return uuid5(NAMESPACE_URL, f"pycil-assistant:{owner_id}:{thread_id}:{run_id}")


def _pending_usage_key(reference: UUID) -> str:
    return f"assistant:usage-pending:{reference}"


def _settlement_status_rank(status: str) -> int:
    return {"interrupted": 0, "disconnected": 1, "failed": 1, "completed": 2}.get(
        status, -1
    )


def _usage_progress(details: dict) -> int:
    usage = details.get("usage")
    if not isinstance(usage, dict):
        return 0
    return int(usage.get("model_calls", len(usage.get("calls", []))))


def _settlement_details(
    context: AssistantContext,
    *,
    status: str,
    run_id: str,
    thread_id: str,
    lease_token: str,
) -> dict:
    return {
        "status": status,
        "run_id": run_id,
        "thread_id": thread_id,
        "lease_token": lease_token,
        "model_id": context.model_id,
        "reasoning_effort": context.reasoning_effort,
        "metering_incomplete": bool(
            context.usage.unmetered_calls
            or context.usage.unpriced_cache_write_tokens
        ),
        "usage": context.usage.to_dict(),
    }


async def _persist_usage(
    reference: UUID, owner_id: UUID, amount: int, details: dict
) -> None:
    async with session_scope() as session:
        await credit.settle_agent_turn(
            session,
            owner_id,
            reference_id=reference,
            amount=amount,
            details=details,
        )
        await session.commit()


async def _settle(
    reference: UUID,
    owner_id: UUID,
    context: AssistantContext,
    *,
    run_id: str,
    thread_id: str,
    status: str,
    redis: Redis,
    lease_token: str,
) -> None:
    """Persist cumulative usage under one logical AG-UI run debit."""
    amount = log_turn_usage(context.usage)
    details = _settlement_details(
        context,
        status=status,
        run_id=run_id,
        thread_id=thread_id,
        lease_token=lease_token,
    )
    pending_key = _pending_usage_key(reference)
    try:
        await redis.set(
            pending_key,
            json.dumps({"amount": amount, "details": details}, separators=(",", ":")),
            ex=_USAGE_PENDING_TTL_SECONDS,
        )
    except Exception:
        # The protected database transaction remains authoritative if Redis is
        # unavailable; the warning makes the reduced retry path visible.
        logger.exception("assistant_usage_pending_store_failed", extra={"run_id": run_id})

    task = asyncio.create_task(_persist_usage(reference, owner_id, amount, details))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        # The pending Redis snapshot lets the next resume finish settlement if
        # cancellation reaches this request before the shielded commit completes.
        raise
    except Exception:
        logger.exception("assistant_usage_settlement_failed", extra={"run_id": run_id})
        return

    with suppress(Exception):
        await redis.delete(pending_key)


async def _load_agent_turn(
    session: AsyncSession, redis: Redis, user_id: UUID, reference: UUID
):
    """Load the prior cumulative meter and replay a pending database settlement."""
    row = await credit.get_agent_turn(session, user_id, reference)
    pending_key = _pending_usage_key(reference)
    raw = await redis.get(pending_key)
    if raw:
        try:
            pending = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            amount = int(pending["amount"])
            details = pending["details"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ServiceUnavailableError("assistant_metering_state_invalid") from error
        saved_details = row.details or {} if row is not None else {}
        pending_status_rank = _settlement_status_rank(details.get("status", ""))
        saved_status_rank = _settlement_status_rank(saved_details.get("status", ""))
        stale_pending = row is not None and (
            amount < row.amount
            or (
                amount == row.amount
                and (
                    _usage_progress(details) <= _usage_progress(saved_details)
                    and pending_status_rank <= saved_status_rank
                )
            )
        )
        if not stale_pending:
            await _persist_usage(reference, user_id, amount, details)
        with suppress(Exception):
            await redis.delete(pending_key)
        row = await credit.get_agent_turn(session, user_id, reference)
        if row is not None:
            await session.refresh(row)
    return row


def _with_graph_resume(body: RunAgentInput) -> RunAgentInput:
    """Translate the client's decision into the shape the graph's middleware reads.

    The client speaks the product's vocabulary — ``{"decision": "approve"}`` — while
    the human-in-the-loop middleware reads LangGraph's own, ``{"decisions":
    [{"type": "approve"}]}``, and looks that key up without a guard. Forwarding the
    client's payload verbatim therefore fails *inside* the middleware with a bare
    ``KeyError``, which the stream can only report as a failed run: the decision was
    valid and the run still died, with nothing naming the mismatch.

    Translating at the boundary is what makes the two ends meet. Validation happens
    here too, so an unknown decision is a 422 rather than a failed turn.
    """
    entry = body.resume[0]
    try:
        decision = ResumeDecision.model_validate(entry.payload)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "invalid resume entry") from exc
    return body.model_copy(
        update={
            "resume": [
                entry.model_copy(update={"payload": {"decisions": [decision.command()]}})
            ]
        }
    )


async def _streamed_events(
    agent,
    body: RunAgentInput,
    context: AssistantContext,
    reference: UUID,
    user_id: UUID,
    redis: Redis,
    graph,
    lease_token: str,
) -> AsyncIterator[bytes]:
    """Run one turn through the adapter, settling exactly once on every exit path."""
    encoder = EventEncoder()
    request_agent = agent.clone()
    request_agent.request_context = context
    status = "incomplete"
    stream_completed = False
    interval = max(1, lease_ttl_seconds() // 3)
    renewal = asyncio.create_task(_renew_turn_lease(redis, user_id, lease_token, interval))
    iterator = request_agent.run(body).__aiter__()
    next_event = asyncio.create_task(anext(iterator))
    try:
        while True:
            done, _ = await asyncio.wait(
                {next_event, renewal}, return_when=asyncio.FIRST_COMPLETED
            )
            if renewal in done:
                renewal.result()
            try:
                event = next_event.result()
            except StopAsyncIteration:
                break
            except Exception:  # noqa: BLE001 - reported as a terminal frame
                # A provider failure must end the stream in the protocol's own
                # vocabulary. Letting it propagate closes the connection mid-body,
                # and the client sees a truncated stream rather than a failed run —
                # so it cannot tell a dead provider from a dropped network, and the
                # turn's lease looks like it is still running. One RUN_ERROR frame
                # is the whole difference between "this run failed" and "unknown".
                #
                # Logged before the frame is sent, because the frame carries a
                # deliberately generic message: without this the cause of a failed
                # turn would exist nowhere at all.
                logger.exception("assistant_run_failed")
                status = "failed"
                yield encoder.encode(_run_error_frame())
                return
            yield encoder.encode(event)
            next_event = asyncio.create_task(anext(iterator))
        stream_completed = True
    except asyncio.CancelledError:
        status = "disconnected"
        raise
    except Exception:
        status = "failed"
        raise
    finally:
        next_event.cancel()
        renewal.cancel()
        await asyncio.gather(next_event, renewal, return_exceptions=True)
        try:
            state = await _thread_state(graph, user_id, UUID(body.thread_id))
            if state.interrupts:
                status = "interrupted"
            elif stream_completed:
                status = "completed"
        except Exception:
            if stream_completed:
                status = "incomplete"
            logger.exception("assistant_checkpoint_state_unavailable")
        await _settle(
            reference,
            user_id,
            context,
            run_id=body.run_id,
            thread_id=body.thread_id,
            status=status,
            redis=redis,
            lease_token=lease_token,
        )


async def _renew_turn_lease(
    redis: Redis, user_id: UUID, token: str, interval_seconds: int
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        if not await renew_turn_lease(redis, user_id, token):
            raise ConflictError("assistant_turn_lease_lost")


def _run_error_frame():
    """The terminal frame for a run that failed mid-stream.

    The message is deliberately generic rather than the exception's text: a provider
    error can embed the request URL, a key fragment or part of the prompt, and this
    frame is delivered to the client. The stable code is what a client switches on.
    """
    return RunErrorEvent(
        message="The assistant run failed.",
        code="assistant_run_failed",
    )


def _sse(events: AsyncIterator[bytes]) -> StreamingResponse:
    async def frames() -> AsyncIterator[bytes]:
        iterator = events.__aiter__()
        pending = asyncio.create_task(anext(iterator))
        try:
            while True:
                done, _ = await asyncio.wait({pending}, timeout=15)
                if not done:
                    yield b": heartbeat\n\n"
                    continue
                try:
                    yield pending.result()
                except StopAsyncIteration:
                    return
                pending = asyncio.create_task(anext(iterator))
        finally:
            pending.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                await pending

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/models", response_model=ModelCatalogRead)
async def list_models(
    user: CurrentUser = Depends(current_user),
) -> ModelCatalogRead:
    """The models a client may select, projected from the server's allowlist.

    Authenticated because the catalog is product policy rather than public data.
    A client selects from this list; it never supplies a model id the server has
    not offered, and it never supplies a price.
    """
    return ModelCatalogRead.from_config()


@router.post("/threads", response_model=ThreadRead, status_code=201)
async def create_thread(
    body: ThreadCreate,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ThreadRead:
    return ThreadRead.model_validate(
        await thread_lifecycle.create_thread(session, owner_id=user.id, title=body.title)
    )


@router.get("/threads", response_model=list[ThreadRead])
async def list_threads(
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ThreadRead]:
    rows = await thread_lifecycle.list_active_threads(session, owner_id=user.id)
    return [ThreadRead.model_validate(row) for row in rows]


@router.get("/threads/{thread_id}", response_model=ThreadRead)
async def get_thread(
    thread_id: UUID,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ThreadRead:
    thread = await require_owned_thread(session, thread_id, user.id)
    await refresh_retention(session, thread)
    return ThreadRead.model_validate(thread)


def _message_dict(message) -> dict:
    if isinstance(message, dict):
        return message
    if hasattr(message, "model_dump"):
        return message.model_dump(mode="json", exclude_none=True)
    return {"content": str(message)}


async def _thread_state(graph, owner_id: UUID, thread_id: UUID) -> ThreadStateRead:
    """The durable conversation, read from the checkpointer.

    The checkpoint is the only conversation store, so this reads what LangGraph
    persisted rather than a second transcript table.
    """
    snapshot = await graph.aget_state(
        {"configurable": {"thread_id": checkpoint_thread_id(owner_id, thread_id)}}
    )
    values = getattr(snapshot, "values", {}) or {}
    messages = [_message_dict(message) for message in values.get("messages", [])]
    interrupts = []
    for interrupt in getattr(snapshot, "interrupts", ()) or ():
        value = getattr(interrupt, "value", interrupt)
        interrupts.append(value if isinstance(value, dict) else {"value": str(value)})
    return ThreadStateRead(messages=messages, interrupts=interrupts)


@router.get("/threads/{thread_id}/state", response_model=ThreadStateRead)
async def get_thread_state(
    thread_id: UUID,
    request: Request,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ThreadStateRead:
    await require_owned_thread(session, thread_id, user.id)
    state = await _thread_state(_graph(request), user.id, thread_id)
    # A paused turn is visible as a pending interrupt in the checkpoint, so the
    # run status is derived from it rather than stored a second time.
    state.status = "interrupted" if state.interrupts else "idle"
    return state


@router.post(
    "/ag-ui",
    responses={**error_responses(401, 404, 409, 413, 422, 503)},
)
async def ag_ui_run(
    body: RunAgentInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
):
    """Run or resume one assistant turn, streamed as AG-UI events."""
    try:
        thread_id = UUID(body.thread_id)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(422, "invalid threadId") from exc

    # Ownership precedes every checkpoint read and tool call. The adapter would
    # otherwise use the client's thread id verbatim as the checkpoint key.
    await require_owned_thread(session, thread_id, user.id)
    agent = _agent(request)
    graph = _graph(request)

    if body.resume:
        if len(body.resume) != 1:
            raise HTTPException(422, "exactly one resume entry is required")
        body = _with_graph_resume(body)
        await revalidate_actor(session, user.id)

    reference = _run_reference(user.id, thread_id, body.run_id)
    saved_turn = await _load_agent_turn(session, redis, user.id, reference)
    model_id, effort = _selection(body)
    resume_lease_token: str | None = None
    if body.resume:
        details = saved_turn.details if saved_turn is not None else None
        if (
            not isinstance(details, dict)
            or details.get("run_id") != body.run_id
            or details.get("thread_id") != str(thread_id)
            or details.get("status") in {"completed", "failed"}
        ):
            raise ConflictError("assistant_run_not_resumable")
        checkpoint_state = await _thread_state(graph, user.id, thread_id)
        if not checkpoint_state.interrupts:
            raise ConflictError("assistant_run_not_resumable")
        resume_lease_token = details.get("lease_token")
        if not isinstance(resume_lease_token, str) or not resume_lease_token:
            raise ServiceUnavailableError("assistant_metering_state_invalid")
        saved_model_id = details.get("model_id")
        saved_effort = details.get("reasoning_effort")
        if not isinstance(saved_model_id, str) or not isinstance(saved_effort, str):
            raise ServiceUnavailableError("assistant_metering_state_invalid")
        if model_id is not None and model_id != saved_model_id:
            raise HTTPException(422, "model cannot change while resuming a run")
        if effort is not None and effort != saved_effort:
            raise HTTPException(422, "reasoning effort cannot change while resuming a run")
        try:
            model, resolved_effort = system_config.resolve_selection(
                saved_model_id, saved_effort
            )
            usage = TurnUsage.from_dict(details["usage"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ServiceUnavailableError("assistant_metering_state_invalid") from exc
    else:
        if saved_turn is not None:
            raise ConflictError("assistant_run_id_reused")
        try:
            model, resolved_effort = system_config.resolve_selection(model_id, effort)
        except ValueError as exc:
            # Refused before any provider call or ledger entry, so a bad selection
            # costs the learner nothing.
            raise HTTPException(422, str(exc)) from exc
        try:
            validate_attachments(body.messages, vision_enabled=model.features.vision)
        except AttachmentRejected as exc:
            # Same reasoning as an unknown model: refuse at ingress, before the
            # admission charge and before any bytes reach the provider.
            raise HTTPException(422, exc.code) from exc
        await credit.require_agent_credit(session, user.id)
        usage = TurnUsage()

    # The stream settles on a separate session. End this read/admission
    # transaction before returning the stream so an on-demand credit row or a
    # database connection is not held for its full duration.
    await session.commit()

    lease = (
        resume_lease_token
        if resume_lease_token
        and await renew_turn_lease(redis, user.id, resume_lease_token)
        else await acquire_turn_lease(redis, user.id)
    )
    if lease is None:
        raise ConflictError("assistant_turn_in_progress")

    context = AssistantContext(
        user_id=user.id,
        model_id=model.id,
        reasoning_effort=resolved_effort,
        usage=usage,
    )
    async def events() -> AsyncIterator[bytes]:
        try:
            async for frame in _streamed_events(
                agent, body, context, reference, user.id, redis, graph, lease
            ):
                yield frame
        finally:
            pending = False
            try:
                pending = bool(
                    (await _thread_state(graph, user.id, thread_id)).interrupts
                )
            except Exception:
                logger.exception("assistant_checkpoint_state_unavailable")
            if pending:
                with suppress(Exception):
                    await renew_turn_lease(
                        redis,
                        user.id,
                        lease,
                        ttl_seconds=pending_lease_ttl_seconds(),
                    )
            else:
                await release_turn_lease(redis, user.id, lease)

    return _sse(events())


@router.post(
    "/threads/{thread_id}/runs/stream",
    responses={**error_responses(401, 404, 409, 413, 422, 503)},
)
async def create_run(
    thread_id: UUID,
    body: MessageCreate,
    request: Request,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
):
    """Start a turn from a plain message, without the client driving AG-UI."""
    if len(body.content) > settings.assistant_max_message_chars:
        raise PayloadTooLargeError("assistant_message_too_long")
    await require_owned_thread(session, thread_id, user.id)
    agent = _agent(request)
    graph = _graph(request)
    model, effort = system_config.resolve_selection()
    await credit.require_agent_credit(session, user.id)
    await session.commit()

    lease = await acquire_turn_lease(redis, user.id)
    if lease is None:
        raise ConflictError("assistant_turn_in_progress")

    run_id = str(uuid4())
    reference = _run_reference(user.id, thread_id, run_id)
    context = AssistantContext(
        user_id=user.id,
        model_id=model.id,
        reasoning_effort=effort,
        usage=TurnUsage(),
    )
    from ag_ui.core import UserMessage

    agent_input = RunAgentInput(
        thread_id=str(thread_id),
        run_id=run_id,
        messages=[UserMessage(id=str(uuid4()), role="user", content=body.content)],
        state=None,
        tools=[],
        context=[],
        forwarded_props={},
    )

    async def events() -> AsyncIterator[bytes]:
        try:
            async for frame in _streamed_events(
                agent,
                agent_input,
                context,
                reference,
                user.id,
                redis,
                graph,
                lease,
            ):
                yield frame
        finally:
            pending = False
            try:
                pending = bool(
                    (await _thread_state(graph, user.id, thread_id)).interrupts
                )
            except Exception:
                logger.exception("assistant_checkpoint_state_unavailable")
            if pending:
                with suppress(Exception):
                    await renew_turn_lease(
                        redis,
                        user.id,
                        lease,
                        ttl_seconds=pending_lease_ttl_seconds(),
                    )
            else:
                await release_turn_lease(redis, user.id, lease)

    return _sse(events())


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: UUID,
    request: Request,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    thread = await require_owned_thread(session, thread_id, user.id)
    await thread_lifecycle.delete_thread(
        session, thread, getattr(request.app.state, "assistant_checkpointer", None)
    )
