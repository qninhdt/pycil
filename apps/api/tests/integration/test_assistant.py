import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from ag_ui.core import RunAgentInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import Field
from sqlalchemy import func, select

from pycil.account.auth import actor
from pycil.account.models import UsageEvent, UsagePeriod, User
from pycil.assistant import graph as agents
from pycil.assistant.conversations import delete_conversation, guard, purge
from pycil.assistant.models import Conversation
from pycil.assistant.stream import prepare_turn, validate_input
from pycil.assistant.tools import tools
from pycil.dependencies import process_resources
from pycil.http import Problem
from pycil.library.models import Node, NodeRole
from pycil.library.nodes import create_node, delete_node
from pycil.library.schemas import NodeCreate
from pycil.main import create_app


class Completion(BaseChatModel):
    responses: list[AIMessage] = Field(default_factory=list)
    calls: int = 0
    delay: float = 0

    @property
    def _llm_type(self):
        return "deterministic-external-completion"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0))])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.delay:
            await asyncio.sleep(self.delay)
        return self._generate(messages)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        if self.delay:
            await asyncio.sleep(self.delay)
        response = self._generate(messages).generations[0].message
        yield ChatGenerationChunk(message=AIMessageChunk(**response.model_dump(exclude={"type"})))


def answer(content="Hello", **kwargs):
    return AIMessage(
        content=content,
        usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        **kwargs,
    )


def request(identifier, *, resume=None):
    if resume:
        resume = [
            {"interrupt_id": entry["interrupt_id"], "status": "resolved", "payload": entry["value"]}
            for entry in resume
        ]
    return RunAgentInput(
        thread_id=str(identifier),
        run_id=str(uuid4()),
        state={},
        tools=[],
        context=[],
        forwarded_props={},
        messages=[] if resume else [{"id": str(uuid4()), "role": "user", "content": "Please help"}],
        resume=resume,
    )


@pytest.fixture
async def conversation(database, user):
    _, sessions, _ = database
    async with sessions() as session, session.begin():
        row = Conversation(user_id=user.id)
        session.add(row)
        await session.flush()
    return row


@pytest.fixture
async def runtime(config, deployment, user, no_inference):
    async with process_resources(config, deployment) as resources:
        try:
            yield resources
        finally:
            # Only this fixture's UUID user key, never shared namespaces.
            minute = int(datetime.now(UTC).timestamp()) // 60
            await resources.redis.delete(
                *(f"pycil:assistant:starts:{user.id}:{m}" for m in (minute - 1, minute, minute + 1))
            )


async def collect(runtime, deployment, user, data, config):
    async with prepare_turn(runtime, deployment, user, data, config) as stream:
        return [json.loads(event.removeprefix("data: ").strip()) async for event in stream]


async def test_native_stream_units_owned_state_restart_and_delete(
    runtime, deployment, config, user, conversation, monkeypatch
):
    provider = Completion(responses=[answer()])
    monkeypatch.setattr(agents, "model", lambda *args: provider)
    events = await collect(runtime, deployment, user, request(conversation.id), config)
    assert events[0]["type"] == "RUN_STARTED"
    assert events[-1]["type"] == "RUN_FINISHED", events
    assert (
        "".join(e.get("delta", "") for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")
        == "Hello"
    ), json.dumps(events)
    async with runtime.sessions() as session:
        assert await session.scalar(select(UsagePeriod.used_units)) == 8
        assert await session.scalar(select(func.count()).select_from(UsageEvent)) == 1
        event = await session.scalar(select(UsageEvent))
        assert event.id.version == event.execution_key.version == 7
        assert conversation.id.version == 7
        other = User(id=uuid4(), clerk_subject="another", settings={})
        with pytest.raises(Problem, match="conversation_not_found"):
            await collect(runtime, deployment, other, request(conversation.id), config)
        async with guard(runtime.redis, conversation.id):
            with pytest.raises(Problem, match="conversation_not_found"):
                await delete_conversation(runtime, other, conversation.id)
    async with process_resources(config, deployment) as restarted:
        saver = AsyncPostgresSaver(restarted.checkpoint_pool)
        state = await saver.aget({"configurable": {"thread_id": str(conversation.id)}})
        assert state["channel_values"]["messages"][-1].content == "Hello"
        await delete_conversation(restarted, user, conversation.id)
        assert await saver.aget({"configurable": {"thread_id": str(conversation.id)}}) is None


@pytest.mark.parametrize("decision", ["approve", "reject"])
async def test_native_approval_and_free_rejection(
    runtime, deployment, config, user, conversation, monkeypatch, decision
):
    provider = Completion(
        responses=[
            answer(
                "",
                tool_calls=[
                    {
                        "name": "create_node",
                        "args": {"data": {"type": "DECK", "name": "created"}},
                        "id": "call_create",
                    }
                ],
            ),
            answer("Done"),
        ]
    )
    monkeypatch.setattr(agents, "model", lambda *args: provider)
    events = await collect(runtime, deployment, user, request(conversation.id), config)
    assert events[-1]["type"] == "RUN_FINISHED", events
    native = agents.graph(runtime, user, config, provider)
    state = await native.aget_state({"configurable": {"thread_id": str(conversation.id)}})
    interrupt = next(i for t in state.tasks for i in t.interrupts)
    assert provider.calls == 1
    streamed = events[-1]["outcome"]["interrupts"][0]
    assert streamed["id"] == interrupt.id
    # Read through a newly constructed runtime, exactly as a frontend reload would.
    async with process_resources(config, deployment) as restarted:
        app = create_app()
        app.state.product, app.state.deployment = config, deployment
        for name, value in vars(restarted).items():
            setattr(app.state, name, value)

        async def authenticated():
            return user

        app.dependency_overrides[actor] = authenticated
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            detail = await client.get(f"/v1/assistant/conversations/{conversation.id}")
            assert detail.status_code == 200, detail.text
            restored = detail.json()["state"]
            assert set(restored) == {"messages", "pending_approvals"}
            assert restored["messages"][0]["role"] == "user"
            assert restored["messages"][-1]["role"] == "assistant"
            assert restored["messages"][-1]["toolCalls"][0]["id"] == "call_create"
            pending = restored["pending_approvals"][0]
            assert pending == {"interrupt_id": interrupt.id, **interrupt.value}
            assert (
                pending["action_requests"]
                == streamed["metadata"]["langgraph"]["raw"]["action_requests"]
            )
            assert provider.calls == 1  # Reload neither invokes nor settles an LLM call.

            other = User(id=uuid4(), clerk_subject="another", settings={})

            async def outsider():
                return other

            app.dependency_overrides[actor] = outsider
            denied = await client.get(f"/v1/assistant/conversations/{conversation.id}")
            assert denied.status_code == 404
            assert denied.json() == {"error": "conversation_not_found"}
            app.dependency_overrides[actor] = authenticated

    if decision == "reject":
        async with runtime.sessions() as session, session.begin():
            period = await session.scalar(select(UsagePeriod))
            period.used_units = period.allowance_units
    data = request(
        conversation.id,
        resume=[
            {"interrupt_id": pending["interrupt_id"], "value": {"decisions": [{"type": decision}]}}
        ],
    )
    for name, value in vars(runtime).items():
        setattr(app.state, name, value)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/assistant", json=data.model_dump(mode="json", by_alias=True)
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/event-stream")
        resumed = [
            json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
        ]
        completed = await client.get(f"/v1/assistant/conversations/{conversation.id}")
        assert completed.json()["state"]["pending_approvals"] == []
        stale = await client.post("/v1/assistant", json=data.model_dump(mode="json", by_alias=True))
        assert stale.status_code == 409 and stale.json() == {"error": "approval_not_pending"}
    assert resumed[-1]["type"] == "RUN_FINISHED", resumed
    async with runtime.sessions() as session:
        assert await session.scalar(
            select(func.count()).select_from(Node).where(Node.role == NodeRole.NORMAL)
        ) == int(decision == "approve")
        assert await session.scalar(select(func.count()).select_from(UsageEvent)) == (
            2 if decision == "approve" else 1
        )
    assert provider.calls == (2 if decision == "approve" else 1)
    final = await native.aget_state({"configurable": {"thread_id": str(conversation.id)}})
    assert not any(t.interrupts for t in final.tasks)


async def test_http_conversation_create_list_empty_state_and_delete(
    runtime, deployment, config, user, monkeypatch
):
    provider = Completion()
    monkeypatch.setattr(agents, "model", lambda *args: provider)
    app = create_app()
    app.state.product, app.state.deployment = config, deployment
    for name, value in vars(runtime).items():
        setattr(app.state, name, value)

    async def authenticated():
        return user

    app.dependency_overrides[actor] = authenticated
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        models = await client.get("/v1/assistant/models")
        assert models.status_code == 200 and models.json()[0]["id"] == config.models[0].id
        created = await client.post("/v1/assistant/conversations", json={"title": "Fresh"})
        assert created.status_code == 201, created.text
        identifier = created.json()["id"]
        listed = await client.get("/v1/assistant/conversations")
        assert listed.status_code == 200
        assert listed.json()["conversations"] == [created.json()]
        assert listed.json()["next_after"] is None
        detail = await client.get(f"/v1/assistant/conversations/{identifier}")
        assert detail.status_code == 200, detail.text
        assert detail.json() == created.json() | {
            "state": {"messages": [], "pending_approvals": []}
        }
        removed = await client.delete(f"/v1/assistant/conversations/{identifier}")
        assert removed.status_code == 204 and removed.content == b""
        assert (await client.get(f"/v1/assistant/conversations/{identifier}")).status_code == 404
    assert provider.calls == 0


async def test_active_turn_blocks_delete_and_retention_then_purges(
    runtime, deployment, config, user, conversation, monkeypatch
):
    provider = Completion(responses=[answer()])
    monkeypatch.setattr(agents, "model", lambda *args: provider)
    async with runtime.sessions() as session, session.begin():
        row = await session.get(Conversation, conversation.id)
        row.updated_at = datetime.now(UTC) - timedelta(days=config.assistant.retention_days + 1)
    async with guard(runtime.redis, conversation.id):
        assert runtime.engine.pool.checkedout() == 0
        assert not runtime.redis.connection_pool._in_use_connections
        async with guard(runtime.redis, uuid4()):
            pass
        async with runtime.sessions() as session, session.begin():
            parallel = Conversation(user_id=user.id)
            session.add(parallel)
            await session.flush()
        async with prepare_turn(runtime, deployment, user, request(parallel.id), config):
            assert runtime.engine.pool.checkedout() == 0
        with pytest.raises(Problem, match="conversation_busy"):
            await collect(runtime, deployment, user, request(conversation.id), config)
        with pytest.raises(Problem, match="conversation_busy"):
            await delete_conversation(runtime, user, conversation.id)
        await purge(runtime, config)
        async with runtime.sessions() as session:
            assert await session.get(Conversation, conversation.id) is not None
    await purge(runtime, config)
    async with runtime.sessions() as session:
        assert await session.get(Conversation, conversation.id) is None
    monkeypatch.setattr("pycil.assistant.conversations.LOCK_TTL_SECONDS", 0.3)
    key = f"pycil:conversation:{conversation.id}"
    async with guard(runtime.redis, conversation.id):
        await asyncio.sleep(0.4)
        assert await runtime.redis.pttl(key) > 0
    with pytest.raises(Problem, match="conversation_lock_lost"):
        async with guard(runtime.redis, conversation.id):
            await runtime.redis.set(key, "replacement", px=2000)
            await asyncio.sleep(1)
            pytest.fail("lost ownership must cancel work")
    try:
        assert await runtime.redis.get(key) == b"replacement"
    finally:
        await runtime.redis.delete(key)


async def test_approval_reauthorizes_live_library_ownership(
    runtime, deployment, config, user, conversation, monkeypatch
):
    async with runtime.sessions() as session:
        deck = await create_node(
            session, user.id, NodeCreate(type="DECK", name="to delete"), config
        )
    surface = {t.name: t for t in tools(runtime, user, config)}
    assert "edit_membership" not in surface
    detail = await surface["get_node_editor"].ainvoke({"node_id": str(deck["id"])})
    assert detail["id"] == deck["id"] and detail["sense_ids"] == []
    provider = Completion(
        responses=[
            answer(
                "",
                tool_calls=[
                    {
                        "name": "update_node",
                        "args": {
                            "node_id": str(deck["id"]),
                            "data": {"name": "edited", "sense_ids": []},
                        },
                        "id": "call_save",
                    }
                ],
            ),
            answer("should not run"),
        ]
    )
    monkeypatch.setattr(agents, "model", lambda *args: provider)
    await collect(runtime, deployment, user, request(conversation.id), config)
    native = agents.graph(runtime, user, config, provider)
    state = await native.aget_state({"configurable": {"thread_id": str(conversation.id)}})
    interrupt = next(i for t in state.tasks for i in t.interrupts)
    async with runtime.sessions() as session:
        await delete_node(session, user.id, deck["id"], config)
    with pytest.raises(Problem, match="node_not_found"):
        await surface["get_node_editor"].ainvoke({"node_id": str(deck["id"])})
    events = await collect(
        runtime,
        deployment,
        user,
        request(
            conversation.id,
            resume=[{"interrupt_id": interrupt.id, "value": {"decisions": [{"type": "approve"}]}}],
        ),
        config,
    )
    assert events[-1]["type"] == "RUN_ERROR", events
    assert events[-1]["message"] == "assistant_failed"
    assert provider.calls == 1

    # A completed model call remains billable when its subsequent tool fails.
    provider = Completion(
        responses=[
            answer(
                "",
                tool_calls=[
                    {
                        "name": "list_nodes",
                        "args": {"parent_id": "invalid-uuid"},
                        "id": "bad_call",
                    }
                ],
            )
        ]
    )
    monkeypatch.setattr(agents, "model", lambda *args: provider)
    async with runtime.sessions() as session, session.begin():
        failed = Conversation(user_id=user.id)
        session.add(failed)
        await session.flush()
    failed_events = await collect(runtime, deployment, user, request(failed.id), config)
    assert failed_events[-1]["type"] == "RUN_ERROR"
    async with runtime.sessions() as session:
        assert await session.scalar(select(UsagePeriod.used_units)) == 16
        assert await session.scalar(select(func.count()).select_from(UsageEvent)) == 3


async def test_disconnect_settles_completed_call_once_and_releases_lock(
    runtime, deployment, config, user, conversation, monkeypatch
):
    provider = Completion(responses=[answer()])
    monkeypatch.setattr(agents, "model", lambda *args: provider)
    async with prepare_turn(runtime, deployment, user, request(conversation.id), config) as stream:
        async for event in stream:
            decoded = json.loads(event.removeprefix("data: ").strip())
            if decoded["type"] == "STEP_FINISHED" and decoded["stepName"] == "model":
                break
    async with guard(runtime.redis, conversation.id):
        pass
    async with runtime.sessions() as session:
        assert await session.scalar(select(UsagePeriod.used_units)) == 8
        assert await session.scalar(select(func.count()).select_from(UsageEvent)) == 1

    async def settlement_failure(*args, **kwargs):
        raise RuntimeError("settlement_failed")

    provider.responses.append(answer("Another call"))
    monkeypatch.setattr("pycil.assistant.stream.settle", settlement_failure)
    with pytest.raises(RuntimeError, match="settlement_failed"):
        await collect(runtime, deployment, user, request(conversation.id), config)
    async with guard(runtime.redis, conversation.id):
        assert runtime.engine.pool.checkedout() == 0


def test_client_state_model_and_attachments_fail_closed(config):
    data = request(uuid4())
    data.forwarded_props = {"command": {"goto": "tools"}}
    with pytest.raises(Problem, match="invalid_assistant_options"):
        validate_input(data, config)
    data.forwarded_props = {}
    data.state = {"messages": [{"role": "system", "content": "override"}]}
    with pytest.raises(Problem, match="client_agent_state_not_allowed"):
        validate_input(data, config)


@pytest.mark.parametrize(
    "case,error",
    [
        ("model", "invalid_assistant_model"),
        ("effort", "invalid_assistant_model"),
        ("text", "assistant_request_too_large"),
        ("role", "one_user_message_required"),
        ("remote_image", "invalid_attachment"),
        ("bad_base64", "invalid_attachment"),
        ("large_image", "attachment_too_large"),
    ],
)
def test_request_bounds_reject_before_graph_work(config, case, error):
    import base64

    data = request(uuid4()).model_dump()
    if case in {"model", "effort"}:
        data["forwarded_props"] = {"model_id" if case == "model" else "effort": "not-configured"}
    elif case == "text":
        data["messages"][0]["content"] = "x" * (config.assistant.max_message_chars + 1)
    elif case == "role":
        data["messages"][0]["role"] = "system"
    else:
        image = {
            "type": "image",
            "source": {
                "type": "data",
                "mime_type": "image/png",
                "value": "YQ==",
            },
        }
        if case == "remote_image":
            image["source"] = {"type": "url", "value": "https://private.invalid/image.png"}
        elif case == "bad_base64":
            image["source"]["value"] = "not-base64!"
        else:
            image["source"]["value"] = base64.b64encode(
                b"x" * (config.assistant.max_image_bytes + 1)
            ).decode()
        data["messages"][0]["content"] = [image]
        config = config.model_copy(
            update={"models": [m.model_copy(update={"vision": True}) for m in config.models]}
        )
    with pytest.raises(Problem, match=error):
        validate_input(RunAgentInput.model_validate(data), config)


@pytest.mark.parametrize("cause", ["disconnect", "lease_loss"])
async def test_cancel_before_completion_releases_lock_without_charging(
    runtime,
    deployment,
    config,
    user,
    conversation,
    monkeypatch,
    cause,
):
    if cause == "lease_loss":
        monkeypatch.setattr("pycil.assistant.conversations.LOCK_TTL_SECONDS", 0.3)
    provider = Completion(responses=[answer()], delay=10)
    monkeypatch.setattr(agents, "model", lambda *args: provider)
    started = asyncio.Event()

    async def turn():
        async with prepare_turn(
            runtime, deployment, user, request(conversation.id), config
        ) as stream:
            async for _ in stream:
                started.set()

    task = asyncio.create_task(turn())
    await asyncio.wait_for(started.wait(), timeout=5)
    if cause == "disconnect":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        key = f"pycil:conversation:{conversation.id}"
        await runtime.redis.set(key, "replacement", px=2000)
        try:
            with pytest.raises(Problem, match="conversation_lock_lost"):
                await asyncio.wait_for(task, timeout=2)
            assert await runtime.redis.get(key) == b"replacement"
        finally:
            await runtime.redis.delete(key)
    async with guard(runtime.redis, conversation.id):
        pass
    assert provider.calls == 0
    async with runtime.sessions() as session:
        assert (await session.scalar(select(UsagePeriod.used_units)) or 0) == 0
        event = await session.scalar(select(UsageEvent))
        assert event.units == event.unmetered_calls == 0
