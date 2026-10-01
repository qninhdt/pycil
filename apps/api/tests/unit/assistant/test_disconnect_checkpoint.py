"""A disconnected stream saves completed steps but not the in-flight model output."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Annotated, TypedDict
from uuid import uuid4

import pytest
from ag_ui.core import RunAgentInput, RunStartedEvent, UserMessage
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph, add_messages

from pycil.assistant.agent.adapter import PycilAgent, checkpoint_thread_id
from pycil.assistant.agent.context import AssistantContext
from pycil.assistant.turns import stream
from pycil.assistant.turns.leases import TurnLease
from pycil.assistant.turns.usage import CallUsage


class _State(TypedDict):
    messages: Annotated[list, add_messages]


class _Agent:
    def __init__(self, graph, entered: asyncio.Event, owner_id, thread_id):
        self.graph = graph
        self.entered = entered
        self.owner_id = owner_id
        self.thread_id = thread_id
        self.request_context = None

    def clone(self):
        return self

    async def run(self, body):
        yield RunStartedEvent(thread_id=body.thread_id, run_id=body.run_id)
        config = {
            "configurable": {"thread_id": checkpoint_thread_id(self.owner_id, self.thread_id)}
        }
        async for _ in self.graph.astream_events(
            {"messages": [HumanMessage(content="delete the folder")]},
            config,
            version="v2",
            durability="exit",
        ):
            pass


@pytest.mark.asyncio
async def test_disconnect_persists_completed_tool_and_discards_inflight_model(monkeypatch):
    owner_id, thread_id = uuid4(), uuid4()
    entered = asyncio.Event()
    tool_calls = []
    model_calls = []

    async def first_model(state):
        return {
            "messages": [
                AIMessage(
                    content="", tool_calls=[{"name": "delete_folder", "args": {}, "id": "tool-1"}]
                )
            ]
        }

    async def tool(state):
        tool_calls.append("deleted")
        return {"messages": [ToolMessage(content="deleted", tool_call_id="tool-1")]}

    async def second_model(state):
        model_calls.append("started")
        entered.set()
        await asyncio.sleep(3600)
        return {"messages": [AIMessage(content="should not be saved")]}

    builder = StateGraph(_State)
    builder.add_node("first_model", first_model)
    builder.add_node("tool", tool)
    builder.add_node("second_model", second_model)
    builder.add_edge(START, "first_model")
    builder.add_edge("first_model", "tool")
    builder.add_edge("tool", "second_model")
    builder.add_edge("second_model", END)
    graph = builder.compile(checkpointer=InMemorySaver())

    settlements = []

    async def settle(**kwargs):
        settlements.append((kwargs["status"], kwargs["context"].usage.model_calls))
        return True

    async def release(redis, lease):
        return True

    monkeypatch.setattr(stream, "_settle", settle)
    monkeypatch.setattr(stream, "release_turn_lease", release)
    context = AssistantContext(user_id=owner_id)
    context.usage.add("gemini-3.8-flash", CallUsage(input_tokens=100, output_tokens=10))
    events = stream._events(
        _Agent(graph, entered, owner_id, thread_id),
        SimpleNamespace(thread_id=str(thread_id), run_id="run-1"),
        context,
        owner_id,
        uuid4(),
        datetime.now(UTC),
        "event-1",
        object(),
        graph,
        TurnLease(owner_id, thread_id, 0, "token"),
        interrupt_id=None,
        free_rejection=False,
    )
    frames = stream._sse(events).body_iterator
    await anext(frames)
    pending = asyncio.create_task(anext(frames))
    await asyncio.wait_for(entered.wait(), timeout=2)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending

    saved = await graph.aget_state(
        {
            "configurable": {
                "thread_id": checkpoint_thread_id(owner_id, thread_id),
            }
        }
    )
    assert [type(message) for message in saved.values["messages"]] == [
        HumanMessage,
        AIMessage,
        ToolMessage,
    ]
    assert saved.values["messages"][-1].content == "deleted"
    assert tool_calls == ["deleted"]
    assert model_calls == ["started"]
    assert settlements == [("disconnected", 1)]


@pytest.mark.asyncio
async def test_adapter_saves_partial_conversation_when_cancelled_during_next_model():
    entered = asyncio.Event()
    executed = []

    @tool
    def delete_folder(folder: str) -> str:
        """Delete a folder."""
        executed.append(folder)
        return "deleted"

    class Model(BaseChatModel):
        calls: int = 0

        @property
        def _llm_type(self):
            return "scripted"

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            raise AssertionError("async model expected")

        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                message = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "delete_folder",
                            "args": {"folder": "old"},
                            "id": "tool-1",
                        }
                    ],
                )
            else:
                entered.set()
                await asyncio.sleep(3600)
                message = AIMessage(content="not completed")
            return ChatResult(generations=[ChatGeneration(message=message)])

    graph = create_agent(Model(), tools=[delete_folder], checkpointer=InMemorySaver())
    agent = PycilAgent(name="pycil-assistant", graph=graph)
    owner_id, thread_id = uuid4(), uuid4()
    agent.request_context = AssistantContext(user_id=owner_id)
    body = RunAgentInput(
        thread_id=str(thread_id),
        run_id="run-1",
        messages=[UserMessage(id="user-1", role="user", content="delete old")],
        tools=[],
        context=[],
        forwarded_props={},
    )

    async def consume():
        async for _ in agent.run(body):
            pass

    task = asyncio.create_task(consume())
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    saved = await graph.aget_state(
        {
            "configurable": {
                "thread_id": checkpoint_thread_id(owner_id, thread_id),
            }
        }
    )
    assert executed == ["old"]
    assert [type(message) for message in saved.values["messages"]] == [
        HumanMessage,
        AIMessage,
        ToolMessage,
    ]
    assert saved.values["messages"][-1].content == "deleted"
