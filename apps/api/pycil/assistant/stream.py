"""Authenticated AG-UI integration and established unit settlement."""

import base64
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing, asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

from ag_ui.core import EventType, RunAgentInput, RunErrorEvent
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from anyio import CancelScope
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError
from sqlalchemy import select, update

from pycil.account.models import User
from pycil.account.plans import Feature
from pycil.account.settings import preferences
from pycil.account.usage import admit, settle
from pycil.app.config import AppConfig
from pycil.app.http import Problem
from pycil.app.settings import Deployment
from pycil.assistant import graph as agents
from pycil.assistant.config import ModelPolicy
from pycil.assistant.conversations import guard, owned
from pycil.assistant.metering import Meter
from pycil.assistant.models import Conversation
from pycil.assistant.schemas import CurrentView
from pycil.infrastructure.observability import get_logger
from pycil.library.nodes import node_details
from pycil.vocabulary.enums import GenerationState, HitKind
from pycil.vocabulary.models import Word

logger = get_logger(__name__)


def validate_input(
    data: RunAgentInput, config: AppConfig
) -> tuple[UUID, ModelPolicy, str, int, int]:
    try:
        identifier = UUID(str(data.thread_id))
    except ValueError, TypeError:
        raise Problem(422, "invalid_conversation_id") from None
    props_raw = data.forwarded_props
    if not isinstance(props_raw, dict) and props_raw is not None:
        raise Problem(422, "invalid_assistant_options")
    props: dict[str, Any] = cast(dict[str, Any], props_raw) if isinstance(props_raw, dict) else {}
    if set(props) - {"model_id", "effort", "current_view"}:
        raise Problem(422, "invalid_assistant_options")
    if props.get("current_view") is not None:
        try:
            CurrentView.model_validate(props["current_view"])
        except ValidationError:
            raise Problem(422, "invalid_assistant_view") from None
    model_id: str = str(props.get("model_id", config.product.assistant.defaults.model))
    policy: ModelPolicy | None = next(
        (p for p in config.product.assistant.models if p.id == model_id),
        None,
    )
    effort: str = str(props.get("effort", config.product.assistant.defaults.effort))
    if policy is None or effort not in policy.efforts:
        raise Problem(422, "invalid_assistant_model")
    if data.state or data.tools or data.context or data.parent_run_id:
        raise Problem(422, "client_agent_state_not_allowed")
    if data.resume:
        if data.messages or len(data.resume) != 1:
            raise Problem(422, "invalid_approval")
    elif len(data.messages) != 1 or getattr(data.messages[0], "role", None) != "user":
        raise Problem(422, "one_user_message_required")
    images, chars = 0, 0
    for message in data.messages:
        content = getattr(message, "content", None)
        if isinstance(content, str):
            chars += len(content)
        elif isinstance(content, list):
            for part in cast(list[Any], content):
                part_type = getattr(part, "type", None)
                if part_type == "text":
                    chars += len(getattr(part, "text", "") or "")
                elif part_type == "image":
                    images += 1
                    source = getattr(part, "source", None)
                    source_val = getattr(source, "value", None)
                    if (
                        not policy.vision
                        or getattr(source, "type", None) != "data"
                        or getattr(source, "mime_type", None)
                        not in {"image/png", "image/jpeg", "image/webp"}
                        or not source_val
                    ):
                        raise Problem(422, "invalid_attachment")
                    try:
                        payload = base64.b64decode(source_val, validate=True)
                    except ValueError:
                        raise Problem(422, "invalid_attachment") from None
                    if len(payload) > config.product.assistant.limits.max_image_bytes:
                        raise Problem(413, "attachment_too_large")
                else:
                    raise Problem(422, "invalid_message_content")
    if (
        chars > config.product.assistant.limits.max_message_chars
        or images > config.product.assistant.limits.max_images
    ):
        raise Problem(413, "assistant_request_too_large")
    return identifier, policy, effort, chars, images


@asynccontextmanager
async def prepare_turn(
    resources: Any,
    deployment: Deployment,
    user: UUID,
    data: RunAgentInput,
    config: AppConfig,
) -> AsyncGenerator[AsyncIterator[str]]:
    identifier, policy, effort, chars, images = validate_input(data, config)
    logger.info(
        "assistant_run_started",
        conversation_id=str(identifier),
        user_id=str(user),
        model_id=policy.id,
        effort=effort,
        message_count=len(data.messages),
        message_chars=chars,
        image_count=images,
    )
    async with resources.sessions() as session:
        await owned(session, user, identifier)
        current = await session.scalar(select(User).where(User.id == user))
        if current is None:
            raise Problem(404, "account_not_found")
        settings = preferences(current.settings, config)
        auto_approve = settings.assistant.auto_approve and not data.resume
        view: dict[str, Any] | None = None
        props_in: object = data.forwarded_props
        props_dict = cast(dict[str, Any], props_in) if isinstance(props_in, dict) else {}
        hint: object | None = props_dict.get("current_view")
        if hint is not None:
            selected = CurrentView.model_validate(hint)
            view = selected.model_dump(mode="json", exclude_none=True)
            if selected.node_id is not None:
                try:
                    detail = await node_details(session, selected.node_id, user, config)
                except Problem as exc:
                    if exc.status != 404:
                        raise
                    view = {"path": selected.path, "unavailable": True}
                else:
                    view |= {"name": detail["name"], "type": detail["type"]}
            elif selected.word_id is not None:
                lemma = await session.scalar(
                    select(Word.lemma).where(
                        Word.id == selected.word_id, Word.generation_state == GenerationState.DONE
                    )
                )
                view = (
                    view | {"name": lemma, "type": HitKind.WORD}
                    if lemma is not None
                    else {"path": selected.path, "unavailable": True}
                )
        context = {
            "now": datetime.now(ZoneInfo(settings.timezone)).isoformat(),
            "timezone": settings.timezone,
            "current_view": view,
            "name": current.display_name,
            "username": current.handle,
        }
        packed = json.dumps(context, ensure_ascii=False, separators=(",", ":"), default=str)
        packed = packed.replace("<", "\\u003c").replace(">", "\\u003e")
        turn_context = f"<context>{packed}</context>"
    async with agents.model(
        deployment, policy, effort, config.runtime.assistant.llm_timeout_seconds
    ) as selected:
        agent = agents.graph(
            resources, user, config, selected, auto_approve=auto_approve, turn_context=turn_context
        )
        checkpoint_config: RunnableConfig = {"configurable": {"thread_id": str(identifier)}}
        async with guard(
            resources.redis, identifier, ttl=config.runtime.assistant.lease_ttl_seconds
        ):
            async with resources.sessions() as session:
                await owned(session, user, identifier)
            state = await agent.aget_state(checkpoint_config)
            if data.resume:
                interrupts = [i for task in state.tasks for i in task.interrupts]
                entry = data.resume[0]
                if len(interrupts) != 1 or entry.interrupt_id != interrupts[0].id:
                    raise Problem(409, "approval_not_pending")
                if entry.status != "resolved" or entry.metadata:
                    raise Problem(422, "invalid_approval")
                payload: object = entry.payload
                actions = cast(list[dict[str, Any]], interrupts[0].value["action_requests"])
                if not isinstance(payload, dict):
                    raise Problem(422, "invalid_approval")
                value = cast(dict[str, Any], payload)
                if set(value) != {"decisions"}:
                    raise Problem(422, "invalid_approval")
                decisions_val: object = value.get("decisions")
                if not isinstance(decisions_val, list):
                    raise Problem(422, "invalid_approval")
                decisions_list = cast(list[dict[str, str]], decisions_val)
                if len(decisions_list) != len(actions) or any(
                    d not in ({"type": "approve"}, {"type": "reject"}) for d in decisions_list
                ):
                    raise Problem(422, "invalid_approval")
                rejection = all(d.get("type") == "reject" for d in decisions_list)
            else:
                if any(task.interrupts for task in state.tasks):
                    raise Problem(409, "approval_pending")
                rejection = False
            moment, key = datetime.now(UTC), uuid7()
            if not rejection:
                async with resources.sessions() as session:
                    try:
                        await admit(session, user, config, Feature.ASSISTANT, moment)
                    except Problem as exc:
                        if exc.status == 403:
                            logger.warning(
                                "assistant_quota_exhausted",
                                user_id=str(user),
                                conversation_id=str(identifier),
                            )
                        raise
                minute = int(moment.timestamp()) // 60
                starts = int(
                    await resources.redis.eval(
                        "local n=redis.call('INCR',KEYS[1]); "
                        "if n==1 then redis.call('EXPIRE',KEYS[1],120) end; return n",
                        1,
                        f"pycil:assistant:starts:{user}:{minute}",
                    )
                    or 0
                )
                if starts > config.runtime.assistant.starts_per_minute:
                    logger.warning(
                        "assistant_rate_limit_exceeded",
                        user_id=str(user),
                        conversation_id=str(identifier),
                    )
                    raise Problem(429, "assistant_start_limit")
            encoder = EventEncoder()

            async def events() -> AsyncGenerator[str]:
                meter = Meter(policy)
                adapter = LangGraphAgent(
                    name="pycil",
                    graph=agent,
                    config={
                        "configurable": {"reject_all": rejection},
                        "callbacks": [meter],
                        "recursion_limit": config.product.assistant.limits.max_tool_calls * 4 + 10,
                    },
                    enable_legacy_on_interrupt_event=False,
                    emit_interrupt_outcome=True,
                    emit_raw_events=False,
                )
                logger.info("assistant_stream_started", conversation_id=str(identifier))
                try:
                    async with aclosing(adapter.run(data)) as native_events:
                        async for event in native_events:
                            if event.type == EventType.RUN_ERROR:
                                event = RunErrorEvent(
                                    type=EventType.RUN_ERROR, message="assistant_failed"
                                )
                            yield encoder.encode(event)
                except Exception:
                    logger.exception(
                        "assistant_stream_failed",
                        conversation_id=str(identifier),
                    )
                    yield encoder.encode(
                        RunErrorEvent(type=EventType.RUN_ERROR, message="assistant_failed")
                    )
                finally:
                    with CancelScope(shield=True):
                        if not rejection:
                            async with resources.sessions() as session:
                                await settle(
                                    session,
                                    user,
                                    config,
                                    execution_key=key,
                                    feature=Feature.ASSISTANT,
                                    units=meter.units,
                                    unmetered_calls=meter.unmetered_calls,
                                    moment=moment,
                                )
                            logger.info(
                                "assistant_units_settled",
                                user_id=str(user),
                                conversation_id=str(identifier),
                                units=meter.units,
                            )
                        async with resources.sessions() as session, session.begin():
                            await session.execute(
                                update(Conversation)
                                .where(Conversation.id == identifier)
                                .values(updated_at=datetime.now(UTC))
                            )
                        logger.info(
                            "assistant_stream_closed",
                            conversation_id=str(identifier),
                            units=meter.units,
                            unmetered_calls=meter.unmetered_calls,
                        )

            iterator = events()
            try:
                yield iterator
            finally:
                with CancelScope(shield=True):
                    await iterator.aclose()
