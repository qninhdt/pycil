"""Authenticated AG-UI integration and established unit settlement."""

import base64
import json
from contextlib import aclosing, asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

from ag_ui.core import EventType, RunErrorEvent
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from anyio import CancelScope
from lexi_ai.contract import Word
from pydantic import ValidationError
from sqlalchemy import select, update

from pycil.account.models import User
from pycil.account.plans import Feature
from pycil.account.schemas import preferences
from pycil.account.usage import admit, settle
from pycil.assistant import graph as agents
from pycil.assistant.conversations import guard, owned
from pycil.assistant.metering import Meter
from pycil.assistant.models import Conversation
from pycil.assistant.schemas import CurrentView
from pycil.http import Problem
from pycil.library.nodes import node_details


def validate_input(data, config):
    try:
        identifier = UUID(data.thread_id)
    except ValueError:
        raise Problem(422, "invalid_conversation_id") from None
    props = data.forwarded_props or {}
    if not isinstance(props, dict) or set(props) - {"model_id", "effort", "current_view"}:
        raise Problem(422, "invalid_assistant_options")
    if props.get("current_view") is not None:
        try:
            CurrentView.model_validate(props["current_view"])
        except ValidationError:
            raise Problem(422, "invalid_assistant_view") from None
    policy = next(
        (p for p in config.models if p.id == props.get("model_id", config.assistant.default_model)),
        None,
    )
    effort = props.get("effort", config.assistant.default_effort)
    if policy is None or effort not in policy.efforts:
        raise Problem(422, "invalid_assistant_model")
    if data.state or data.tools or data.context or data.parent_run_id:
        raise Problem(422, "client_agent_state_not_allowed")
    if data.resume:
        if data.messages or len(data.resume) != 1:
            raise Problem(422, "invalid_approval")
    elif len(data.messages) != 1 or data.messages[0].role != "user":
        raise Problem(422, "one_user_message_required")
    images, chars = 0, 0
    for message in data.messages:
        if isinstance(message.content, str):
            chars += len(message.content)
        else:
            for part in message.content:
                if part.type == "text":
                    chars += len(part.text)
                elif part.type == "image":
                    images += 1
                    source = part.source
                    if (
                        not policy.vision
                        or source.type != "data"
                        or source.mime_type not in {"image/png", "image/jpeg", "image/webp"}
                        or not source.value
                    ):
                        raise Problem(422, "invalid_attachment")
                    try:
                        payload = base64.b64decode(source.value, validate=True)
                    except ValueError:
                        raise Problem(422, "invalid_attachment") from None
                    if len(payload) > config.assistant.max_image_bytes:
                        raise Problem(413, "attachment_too_large")
                else:
                    raise Problem(422, "invalid_message_content")
    if chars > config.assistant.max_message_chars or images > config.assistant.max_images:
        raise Problem(413, "assistant_request_too_large")
    return identifier, policy, effort


@asynccontextmanager
async def prepare_turn(resources, deployment, user, data, config):
    identifier, policy, effort = validate_input(data, config)
    async with resources.sessions() as session:
        await owned(session, user.id, identifier)
        saved_settings = await session.scalar(select(User.settings).where(User.id == user.id))
        if saved_settings is None:
            raise Problem(404, "account_not_found")
        settings = preferences(saved_settings, config)
        auto_approve = settings.assistant.auto_approve and not data.resume
        view = None
        hint = (data.forwarded_props or {}).get("current_view")
        if hint is not None:
            selected = CurrentView.model_validate(hint)
            view = selected.model_dump(mode="json", exclude_none=True)
            if selected.node_id is not None:
                try:
                    detail = await node_details(session, selected.node_id, user.id, config)
                except Problem as exc:
                    if exc.status != 404:
                        raise
                    view = {"path": selected.path, "unavailable": True}
                else:
                    view |= {"name": detail["name"], "type": detail["type"]}
            elif selected.word_id is not None:
                lemma = await session.scalar(
                    select(Word.lemma).where(
                        Word.id == selected.word_id, Word.generation_state == "DONE"
                    )
                )
                view = (
                    view | {"name": lemma, "type": "WORD"}
                    if lemma is not None
                    else {"path": selected.path, "unavailable": True}
                )
        context = {
            "now": datetime.now(ZoneInfo(settings.timezone)).isoformat(),
            "timezone": settings.timezone,
            "current_view": view,
            "name": user.display_name,
            "username": user.handle,
        }
        packed = json.dumps(context, ensure_ascii=False, separators=(",", ":"), default=str)
        packed = packed.replace("<", "\\u003c").replace(">", "\\u003e")
        turn_context = f"<context>{packed}</context>"
    async with agents.model(
        deployment, policy, effort, config.assistant.llm_timeout_seconds
    ) as selected:
        agent = agents.graph(
            resources, user, config, selected, auto_approve=auto_approve, turn_context=turn_context
        )
        checkpoint_config = {"configurable": {"thread_id": str(identifier)}}
        async with guard(resources.redis, identifier):
            async with resources.sessions() as session:
                await owned(session, user.id, identifier)
            state = await agent.aget_state(checkpoint_config)
            if data.resume:
                interrupts = [i for task in state.tasks for i in task.interrupts]
                entry = data.resume[0]
                if len(interrupts) != 1 or entry.interrupt_id != interrupts[0].id:
                    raise Problem(409, "approval_not_pending")
                if entry.status != "resolved" or entry.metadata:
                    raise Problem(422, "invalid_approval")
                value = entry.payload
                actions = interrupts[0].value["action_requests"]
                if (
                    not isinstance(value, dict)
                    or set(value) != {"decisions"}
                    or not isinstance(value["decisions"], list)
                    or len(value["decisions"]) != len(actions)
                    or any(
                        d not in ({"type": "approve"}, {"type": "reject"})
                        for d in value["decisions"]
                    )
                ):
                    raise Problem(422, "invalid_approval")
                rejection = all(d["type"] == "reject" for d in value["decisions"])
            else:
                if any(task.interrupts for task in state.tasks):
                    raise Problem(409, "approval_pending")
                rejection = False
            moment, key = datetime.now(UTC), uuid7()
            if not rejection:
                async with resources.sessions() as session:
                    await admit(session, user.id, config, Feature.ASSISTANT, moment)
                minute = int(moment.timestamp()) // 60
                starts = await resources.redis.eval(
                    "local n=redis.call('INCR',KEYS[1]); "
                    "if n==1 then redis.call('EXPIRE',KEYS[1],120) end; return n",
                    1,
                    f"pycil:assistant:starts:{user.id}:{minute}",
                )
                if starts > config.assistant.starts_per_minute:
                    raise Problem(429, "assistant_start_limit")
            encoder = EventEncoder()

            async def events():
                meter = Meter(policy)
                adapter = LangGraphAgent(
                    name="pycil",
                    graph=agent,
                    config={
                        "configurable": {"reject_all": rejection},
                        "callbacks": [meter],
                        "recursion_limit": config.assistant.max_tool_calls * 4 + 10,
                    },
                    enable_legacy_on_interrupt_event=False,
                    emit_interrupt_outcome=True,
                    emit_raw_events=False,
                )
                try:
                    async with aclosing(adapter.run(data)) as native_events:
                        async for event in native_events:
                            if event.type == EventType.RUN_ERROR:
                                event = RunErrorEvent(
                                    type=EventType.RUN_ERROR, message="assistant_failed"
                                )
                            yield encoder.encode(event)
                except Exception:
                    yield encoder.encode(
                        RunErrorEvent(type=EventType.RUN_ERROR, message="assistant_failed")
                    )
                finally:
                    with CancelScope(shield=True):
                        if not rejection:
                            async with resources.sessions() as session:
                                await settle(
                                    session,
                                    user.id,
                                    config,
                                    execution_key=key,
                                    feature=Feature.ASSISTANT,
                                    units=meter.units,
                                    unmetered_calls=meter.unmetered_calls,
                                    moment=moment,
                                )
                        async with resources.sessions() as session, session.begin():
                            await session.execute(
                                update(Conversation)
                                .where(Conversation.id == identifier)
                                .values(updated_at=datetime.now(UTC))
                            )

            iterator = events()
            try:
                yield iterator
            finally:
                with CancelScope(shield=True):
                    await iterator.aclose()
