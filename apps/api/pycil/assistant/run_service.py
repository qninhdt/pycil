"""Run lifecycle, recoverable SSE events, and graph invocation."""

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from langgraph.types import Command
from sqlalchemy import select

from pycil.assistant.context import AssistantContext
from pycil.assistant.hitl import create_pending_action
from pycil.assistant.models import AssistantRun, AssistantRunEvent, RunStatus
from pycil.assistant.persistence import retention_deadline
from pycil.common.errors import ConflictError
from pycil.config import settings
from pycil.db.redis import get_redis
from pycil.db.session import async_session_factory


def checkpoint_thread_id(owner_id: UUID, thread_id: UUID) -> str:
    return f"assistant:{owner_id}:{thread_id}"


async def checkpoint_version(graph, config: dict) -> str:
    """Read LangGraph's actual checkpoint id, never a local run surrogate."""
    get_state = getattr(graph, "aget_state", None)
    if get_state is None:
        return "unknown"
    snapshot = await get_state(config)
    configurable = getattr(snapshot, "config", {}).get("configurable", {})
    return str(configurable.get("checkpoint_id") or "unknown")


async def acquire_lease(owner_id: UUID, thread_id: UUID, run_id: UUID) -> bool:
    """Atomically enforce run, rate, and reserved monthly-spend capacity."""
    ttl = max(1, settings.assistant_run_deadline_seconds)
    redis = get_redis()
    thread_key = f"assistant:run:{owner_id}:{thread_id}"
    user_key = f"assistant:concurrent:user:{owner_id}"
    global_key = "assistant:concurrent:global"
    now = datetime.now(UTC)
    rate_key = f"assistant:rate:{owner_id}:{now:%Y%m%d%H%M}"
    spend_key = f"assistant:spend:{now:%Y%m}"
    reservation = (
        settings.assistant_max_output_tokens
        / 1000
        * settings.assistant_estimated_cost_per_1k_tokens_usd
    )
    script = """
    if redis.call('GET', KEYS[1]) then return 0 end
    local user_count = tonumber(redis.call('GET', KEYS[2]) or '0')
    if user_count >= tonumber(ARGV[2]) then return 0 end
    local global_count = tonumber(redis.call('GET', KEYS[3]) or '0')
    if global_count >= tonumber(ARGV[3]) then return 0 end
    local rate_count = tonumber(redis.call('GET', KEYS[4]) or '0')
    if rate_count >= tonumber(ARGV[5]) then return 0 end
    local spend = tonumber(redis.call('GET', KEYS[5]) or '0')
    if tonumber(ARGV[6]) > 0 and spend + tonumber(ARGV[7]) > tonumber(ARGV[6]) then return 0 end
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[4])
    redis.call('INCR', KEYS[2]); redis.call('EXPIRE', KEYS[2], ARGV[4])
    redis.call('INCR', KEYS[3]); redis.call('EXPIRE', KEYS[3], ARGV[4])
    redis.call('INCR', KEYS[4]); redis.call('EXPIRE', KEYS[4], 120)
    if tonumber(ARGV[6]) > 0 then
      redis.call('INCRBYFLOAT', KEYS[5], ARGV[7]); redis.call('EXPIRE', KEYS[5], 2678400)
    end
    return 1
    """
    return bool(
        await redis.eval(
            script,
            5,
            thread_key,
            user_key,
            global_key,
            rate_key,
            spend_key,
            str(run_id),
            settings.assistant_per_user_concurrency,
            settings.assistant_global_concurrency,
            ttl,
            settings.assistant_requests_per_minute,
            settings.assistant_monthly_budget_usd,
            reservation,
        )
    )


async def release_lease(owner_id: UUID, thread_id: UUID, run_id: UUID) -> None:
    key = f"assistant:run:{owner_id}:{thread_id}"
    redis = get_redis()
    if await redis.get(key) == str(run_id):
        await redis.delete(key)
        for counter_key in (f"assistant:concurrent:user:{owner_id}", "assistant:concurrent:global"):
            current = await redis.decr(counter_key)
            if current <= 0:
                await redis.delete(counter_key)


async def append_event(run_id: UUID, event_type: str, payload: dict) -> AssistantRunEvent:
    """Persist a sanitized event before making it available to an SSE client."""
    async with async_session_factory() as session:
        run = await session.scalar(
            select(AssistantRun).where(AssistantRun.id == run_id).with_for_update()
        )
        if run is None:
            raise ConflictError("assistant_run_not_found")
        run.event_cursor += 1
        event = AssistantRunEvent(
            run_id=run_id,
            sequence=run.event_cursor,
            event_type=event_type,
            sanitized_payload=payload,
            expires_at=retention_deadline(),
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event


async def set_run_status(run_id: UUID, status: RunStatus, error_code: str | None = None) -> None:
    async with async_session_factory() as session:
        run = await session.get(AssistantRun, run_id)
        if run is not None:
            run.status = status
            run.error_code = error_code
            await session.commit()


def _token_payload(chunk: Any) -> dict | None:
    content = getattr(chunk, "content", None)
    if isinstance(content, str) and content:
        return {"content": content}
    return None


def _interrupt_tool(update: Any) -> tuple[str, dict] | None:
    """Extract a proposed tool call without retaining raw model/provider data."""
    if not isinstance(update, dict):
        return None
    values = update.get("__interrupt__")
    if not values:
        return None
    value = values[0] if isinstance(values, list | tuple) else values
    payload = getattr(value, "value", value)
    if not isinstance(payload, dict):
        return None
    action_requests = payload.get("action_requests") or []
    if not action_requests:
        return None
    request = action_requests[0]
    if not isinstance(request, dict):
        return None
    return str(request.get("name", "unknown")), dict(request.get("args") or {})


def _tool_events(update: Any) -> list[tuple[str, dict]]:
    """Map LangGraph updates to compact provider-independent tool events."""
    if not isinstance(update, dict):
        return []
    events: list[tuple[str, dict]] = []
    for value in update.values():
        messages = value.get("messages", []) if isinstance(value, dict) else []
        for message in messages:
            for call in getattr(message, "tool_calls", []) or []:
                events.append(("tool_call", {"tool": call.get("name", "unknown")}))
            name = getattr(message, "name", None)
            if name:
                content = getattr(message, "content", "")
                events.append(("tool_result", {"tool": name, "content": str(content)[:1000]}))
    return events


async def stream_run(
    graph,
    run: AssistantRun,
    context: AssistantContext,
    content: str | None = None,
    resume: str | None = None,
    lease_acquired: bool = False,
):
    """Yield persisted event rows as graph output arrives; no request DB session is retained."""
    acquired_here = False
    if not lease_acquired and not await acquire_lease(context.user_id, run.thread_id, run.id):
        raise ConflictError("assistant_thread_run_active")
    acquired_here = not lease_acquired
    config = {"configurable": {"thread_id": checkpoint_thread_id(context.user_id, run.thread_id)}}
    try:
        await set_run_status(run.id, RunStatus.RUNNING)
        if resume is None:
            request: Any = {"messages": [{"role": "user", "content": content or ""}]}
        else:
            request = Command(resume={"decisions": [{"type": resume}]})
        async with asyncio.timeout(settings.assistant_run_deadline_seconds):
            async for mode, update in graph.astream(
                request, config=config, context=context, stream_mode=["updates", "messages"]
            ):
                if mode == "messages":
                    token = _token_payload(update[0] if isinstance(update, tuple) else update)
                    if token:
                        yield await append_event(run.id, "token", token)
                elif mode == "updates":
                    for event_type, payload in _tool_events(update):
                        yield await append_event(run.id, event_type, payload)
                    interrupted = _interrupt_tool(update)
                    if interrupted:
                        tool, arguments = interrupted
                        async with async_session_factory() as session:
                            generation = None
                            generations: dict[str, int] = {}
                            # What the approval is *about*, in words. The confirmable
                            # tools are the destructive ones, and an approval prompt
                            # naming only the tool asks the learner to authorise
                            # "delete_node" against an opaque UUID. The target row is
                            # already loaded here for the generation check, so its name
                            # costs nothing extra and is the difference between
                            # informed consent and a blind yes.
                            targets: dict[str, str] = {}
                            from pycil.hierarchy.models import Node

                            for key in ("node_id", "deck_id", "parent_id"):
                                raw_target = arguments.get(key)
                                if raw_target is None:
                                    continue
                                try:
                                    target = await session.get(Node, UUID(str(raw_target)))
                                except ValueError:
                                    continue
                                # Ownership is already required, so echoing the name
                                # back discloses nothing the caller cannot already read.
                                if target is not None and target.author_id == context.user_id:
                                    generations[key] = target.structural_generation
                                    targets[key] = target.name
                                    if key in {"node_id", "deck_id"}:
                                        generation = target.structural_generation
                            arguments = {**arguments, "_resource_generations": generations}
                            action = await create_pending_action(
                                session,
                                run_id=run.id,
                                owner_id=context.user_id,
                                tool=tool,
                                arguments=arguments,
                                checkpoint_version=await checkpoint_version(graph, config),
                                resource_generation=generation,
                            )
                        await set_run_status(run.id, RunStatus.INTERRUPTED)
                        yield await append_event(
                            run.id,
                            "confirmation_required",
                            {
                                "action_id": str(action.id),
                                "tool": tool,
                                "expires_at": action.expires_at.isoformat(),
                                # Only the owned names resolved above, never the raw
                                # argument dict: that also holds ids and the internal
                                # `_resource_generations`, none of which belong in a
                                # payload the client renders. Absent when the tool
                                # targets nothing nameable.
                                "targets": targets,
                            },
                        )
                        return
        await set_run_status(run.id, RunStatus.SUCCEEDED)
        yield await append_event(run.id, "done", {})
    except TimeoutError:
        await set_run_status(run.id, RunStatus.FAILED, "deadline_exceeded")
        yield await append_event(run.id, "error", {"code": "deadline_exceeded"})
    except Exception:
        await set_run_status(run.id, RunStatus.FAILED, "execution_failed")
        yield await append_event(run.id, "error", {"code": "execution_failed"})
    finally:
        if acquired_here or lease_acquired:
            await release_lease(context.user_id, run.thread_id, run.id)
