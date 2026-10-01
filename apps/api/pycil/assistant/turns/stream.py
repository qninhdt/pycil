"""Admission, execution, streaming, and cleanup for one assistant turn."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID, uuid7

from ag_ui.core import RunAgentInput, RunErrorEvent
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.auth import current_user
from pycil.account.schemas import CurrentUser
from pycil.assistant import threads
from pycil.assistant.agent.adapter import checkpoint_thread_id
from pycil.assistant.agent.attachments import AttachmentRejected, validate_attachments
from pycil.assistant.agent.context import AssistantContext
from pycil.assistant.agent.middleware import log_turn_usage
from pycil.assistant.schemas import ResumeDecision
from pycil.assistant.thread_access import require_owned_thread, revalidate_actor
from pycil.assistant.turns.leases import (
    TurnLease,
    acquire_turn_lease,
    check_start_rate,
    lease_ttl_seconds,
    release_turn_lease,
    renew_turn_lease,
)
from pycil.assistant.turns.settlement import settle_assistant_segment
from pycil.assistant.turns.usage import TurnUsage
from pycil.billing.errors import UsageQuotaExhaustedError
from pycil.billing.ledger import get_usage_allowance, require_usage_allowed
from pycil.billing.plans import FeatureKey
from pycil.platform.database import get_session, session_scope
from pycil.platform.errors import (
    ConflictError,
    PayloadTooLargeError,
    ServiceUnavailableError,
    TooManyRequestsError,
    error_responses,
)
from pycil.platform.product_config import system_config
from pycil.platform.redis import get_redis
from pycil.platform.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _runtime(request: Request):
    agent = getattr(request.app.state, "assistant_agent", None)
    graph = getattr(request.app.state, "assistant_graph", None)
    if agent is None or graph is None:
        raise ServiceUnavailableError("assistant_not_configured", code="assistant_not_configured")
    return agent, graph


def _selection(body: RunAgentInput) -> tuple[str | None, str | None]:
    props = body.forwarded_props or {}
    if not isinstance(props, dict):
        return None, None
    model_id = props.get("model") or props.get("modelId")
    effort = props.get("reasoningEffort") or props.get("reasoning_effort")
    return (
        model_id if isinstance(model_id, str) else None,
        effort if isinstance(effort, str) else None,
    )


def _resume(body: RunAgentInput, action_count: int) -> tuple[RunAgentInput, bool]:
    entry = body.resume[0]
    if entry.status != "resolved":
        raise HTTPException(422, "only resolved approval decisions are supported")
    try:
        payload = entry.payload
        if not isinstance(payload, dict) or not isinstance(payload.get("decisions"), list):
            raise ValueError("decisions_required")
        decisions = [ResumeDecision(decision=value) for value in payload["decisions"]]
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "invalid resume entry") from exc
    if len(decisions) != action_count:
        raise HTTPException(422, "one decision per pending action is required")
    translated = body.model_copy(
        update={
            "resume": [
                entry.model_copy(
                    update={
                        "payload": {"decisions": [decision.command() for decision in decisions]}
                    }
                )
            ]
        }
    )
    return translated, all(decision.decision == "reject" for decision in decisions)


async def _settle(
    *,
    user_id: UUID,
    period_id: UUID,
    occurred_at: datetime,
    event_key: str,
    run_id: str,
    status: str,
    context: AssistantContext,
    interrupt_id: str | None,
    thread_id: UUID,
) -> bool:
    for attempt in range(3):
        try:
            async with session_scope() as session:
                await settle_assistant_segment(
                    session,
                    user_id=user_id,
                    period_id=period_id,
                    occurred_at=occurred_at,
                    event_key=event_key,
                    run_id=run_id,
                    status=status,
                    usage=context.usage,
                    interrupt_id=interrupt_id,
                    thread_id=str(thread_id),
                    model_id=context.model_id,
                    reasoning_effort=context.reasoning_effort,
                )
                await session.commit()
            return True
        except Exception:
            logger.exception("assistant_segment_settlement_failed", extra={"run_id": run_id})
            if attempt < 2:
                await asyncio.sleep(0.1 * (attempt + 1))
    return False


async def _renew(redis: Redis, lease: TurnLease) -> None:
    while True:
        await asyncio.sleep(max(1, lease_ttl_seconds() // 3))
        if not await renew_turn_lease(redis, lease):
            raise ConflictError("assistant_turn_lease_lost")


async def _events(
    agent,
    body: RunAgentInput,
    context: AssistantContext,
    user_id: UUID,
    period_id: UUID,
    occurred_at: datetime,
    event_key: str,
    redis: Redis,
    graph,
    lease: TurnLease,
    *,
    interrupt_id: str | None,
    free_rejection: bool,
) -> AsyncIterator[bytes]:
    encoder = EventEncoder()
    request_agent = agent.clone()
    request_agent.request_context = context
    iterator = request_agent.run(body).__aiter__()
    next_event = asyncio.create_task(anext(iterator))
    renewal = asyncio.create_task(_renew(redis, lease))
    status = "incomplete"
    terminal = None
    completed = disconnected = settled = False
    final_status = "incomplete"
    try:
        while True:
            done, _ = await asyncio.wait({next_event, renewal}, return_when=asyncio.FIRST_COMPLETED)
            if renewal in done:
                renewal.result()
            try:
                event = next_event.result()
            except StopAsyncIteration:
                completed = True
                break
            if getattr(event, "type", None) in {"RUN_FINISHED", "RUN_ERROR"}:
                terminal = event
                if event.type == "RUN_ERROR":
                    status = "failed"
            else:
                yield encoder.encode(event)
            next_event = asyncio.create_task(anext(iterator))
    except asyncio.CancelledError, GeneratorExit:
        disconnected = True
        status = "disconnected"
        raise
    except Exception:
        status = "failed"
        logger.exception("assistant_run_failed", extra={"run_id": body.run_id})
    finally:

        async def cleanup() -> tuple[bool, str]:
            nonlocal final_status
            # Finish unwinding the graph before reading or settling: with exit-only
            # durability LangGraph saves completed steps on cancellation as well as
            # on normal exit. Reading before this task stops would see the old state.
            next_event.cancel()
            renewal.cancel()
            await asyncio.gather(next_event, renewal, return_exceptions=True)
            with suppress(Exception):
                await iterator.aclose()
            try:
                checkpoint = await threads.read_state(graph, user_id, lease.thread_id)
                final_status = (
                    status
                    if status in {"failed", "disconnected"}
                    else "interrupted"
                    if checkpoint.interrupts
                    else "completed"
                    if completed
                    else "incomplete"
                )
            except Exception:
                logger.exception("assistant_checkpoint_state_unavailable")
                final_status = "incomplete" if completed else status
            log_turn_usage(context.usage)
            try:
                result = await _settle(
                    user_id=user_id,
                    period_id=period_id,
                    occurred_at=occurred_at,
                    event_key=event_key,
                    run_id=body.run_id,
                    status="cancelled" if free_rejection and not disconnected else final_status,
                    context=context,
                    interrupt_id=interrupt_id,
                    thread_id=lease.thread_id,
                )
                return result, final_status
            finally:
                await release_turn_lease(redis, lease)

        task = asyncio.create_task(cleanup())
        try:
            settled, final_status = await asyncio.wait_for(asyncio.shield(task), timeout=10)
        except asyncio.CancelledError:
            with suppress(Exception):
                await asyncio.wait_for(asyncio.shield(task), timeout=10)
            raise
        except Exception:
            logger.exception("assistant_turn_cleanup_failed")
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    if not disconnected:
        if completed and settled and final_status in {"completed", "interrupted"} and terminal:
            yield encoder.encode(terminal)
        else:
            yield encoder.encode(
                RunErrorEvent(message="The assistant run failed.", code="assistant_run_failed")
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
            await asyncio.gather(pending, return_exceptions=True)
            close = asyncio.create_task(iterator.aclose())
            with suppress(Exception):
                await asyncio.wait_for(asyncio.shield(close), timeout=10)

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _message_chars(body: RunAgentInput) -> int:
    total = 0
    for message in body.messages:
        if getattr(message, "role", None) != "user":
            continue
        content = getattr(message, "content", "")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            total += sum(
                len(text)
                for part in content
                if isinstance((text := getattr(part, "text", None)), str)
            )
    return total


async def run_turn(
    body: RunAgentInput,
    request: Request,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
):
    try:
        thread_id = UUID(body.thread_id)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(422, "invalid threadId") from exc
    if _message_chars(body) > settings.assistant_max_message_chars:
        raise PayloadTooLargeError("assistant_message_too_long")
    await require_owned_thread(session, thread_id, user.id)
    agent, graph = _runtime(request)
    checkpoint = await threads.read_state(graph, user.id, thread_id)
    model_id, effort = _selection(body)
    interrupt_id = None
    free_rejection = all_rejected = False

    if body.resume:
        if len(body.resume) != 1 or not checkpoint.interrupts:
            raise ConflictError("assistant_run_not_resumable")
        interrupt_id = body.resume[0].interrupt_id
        actions = checkpoint.interrupts[0].get("action_requests", [])
        if not actions:
            raise ConflictError("assistant_run_not_resumable")
        body, all_rejected = _resume(body, len(actions))
        await revalidate_actor(session, user.id)
        snapshot = await graph.aget_state(
            {"configurable": {"thread_id": checkpoint_thread_id(user.id, thread_id)}}
        )
        values = getattr(snapshot, "values", {}) or {}
        saved_model_id = values.get("selected_model_id")
        saved_effort = values.get("selected_effort")
        if not saved_model_id or not saved_effort:
            raise ConflictError("assistant_pending_model_unavailable")
        if model_id is not None and model_id != saved_model_id:
            raise HTTPException(422, "model cannot change while resuming a run")
        if effort is not None and effort != saved_effort:
            raise HTTPException(422, "reasoning effort cannot change while resuming a run")
        model_id, effort = saved_model_id, saved_effort
    elif checkpoint.interrupts:
        raise ConflictError("assistant_run_waiting_for_approval")

    try:
        model, resolved_effort = system_config.resolve_selection(model_id, effort)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not body.resume:
        try:
            validate_attachments(body.messages, vision_enabled=model.features.vision)
        except AttachmentRejected as exc:
            raise HTTPException(422, exc.code) from exc

    started_at = datetime.now(UTC)
    try:
        balance = await require_usage_allowed(
            session, user.id, feature=FeatureKey.ASSISTANT, moment=started_at
        )
    except UsageQuotaExhaustedError:
        if not body.resume or not all_rejected:
            raise
        balance = await get_usage_allowance(session, user.id, moment=started_at)
        free_rejection = True

    retry_after = await check_start_rate(redis, user.id)
    if retry_after is not None:
        raise TooManyRequestsError("assistant_start_rate_limited", retry_after=retry_after)
    await session.commit()
    lease = await acquire_turn_lease(redis, user.id, thread_id, balance.plan)
    if lease is None:
        raise ConflictError("assistant_turn_in_progress")
    context = AssistantContext(
        user_id=user.id,
        model_id=model.id,
        reasoning_effort=resolved_effort,
        usage=TurnUsage(),
    )
    return _sse(
        _events(
            agent,
            body,
            context,
            user.id,
            balance.period_id,
            started_at,
            f"assistant:{user.id}:{uuid7().hex}",
            redis,
            graph,
            lease,
            interrupt_id=interrupt_id,
            free_rejection=free_rejection,
        )
    )


def register_turn_routes(target_router: APIRouter) -> None:
    target_router.post(
        "",
        responses={**error_responses(401, 404, 409, 413, 422, 429, 503)},
    )(run_turn)
