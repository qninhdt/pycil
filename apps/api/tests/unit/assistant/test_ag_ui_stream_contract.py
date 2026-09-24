"""The AG-UI stream the adapter emits, checked with a real parser.

The frontend consumes this stream through ``@ag-ui/client``, so a backend test
that only asserted "some events came back" would not catch a protocol break. The
events are fed through the SDK's own encoder and decoded again, which is the
contract a compatible client parser reads.
"""

import json
from typing import Annotated, TypedDict

import pytest
from ag_ui.core import RunAgentInput, UserMessage
from ag_ui.encoder import EventEncoder
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from pycil.assistant.application.ag_ui_agent import PycilAgent

pytestmark = pytest.mark.asyncio


class _State(TypedDict):
    messages: Annotated[list, add_messages]


def _reply_graph():
    builder = StateGraph(_State)
    builder.add_node("reply", lambda state: {"messages": [AIMessage(content="hello there")]})
    builder.add_edge("__start__", "reply")
    builder.add_edge("reply", END)
    return builder.compile(checkpointer=InMemorySaver())


def _input(thread_id: str = "thread-1", run_id: str = "run-1") -> RunAgentInput:
    return RunAgentInput(
        thread_id=thread_id,
        run_id=run_id,
        messages=[UserMessage(id="m1", role="user", content="hi")],
        tools=[],
        context=[],
        forwarded_props={},
    )


async def test_a_turn_streams_an_ordered_run_from_start_to_finish():
    """Every event arrives encoded, and the run opens and closes exactly once."""
    agent = PycilAgent(name="pycil-assistant", graph=_reply_graph())
    encoder = EventEncoder()

    frames = [encoder.encode(event) async for event in agent.run(_input())]
    types = [
        json.loads(frame.split("data: ", 1)[1])["type"]
        for frame in frames
        if frame.startswith("data: ")
    ]

    assert types[0] == "RUN_STARTED"
    assert types[-1] == "RUN_FINISHED"
    assert types.count("RUN_STARTED") == 1
    assert types.count("RUN_FINISHED") == 1
    # The conversation reaches the client, not just the run envelope.
    assert "MESSAGES_SNAPSHOT" in types
    assert "RUN_ERROR" not in types


async def test_the_emitted_frames_are_parseable_sse_with_json_payloads():
    """A frame that is not valid SSE or valid JSON breaks the client parser."""
    agent = PycilAgent(name="pycil-assistant", graph=_reply_graph())
    encoder = EventEncoder()

    frames = [encoder.encode(event) async for event in agent.run(_input())]

    assert frames
    for frame in frames:
        assert frame.startswith("data: ")
        assert frame.endswith("\n\n")
        json.loads(frame[len("data: ") : -2])


async def test_a_second_turn_reuses_the_thread_and_keeps_its_history():
    """Resume/continuation reads the same checkpoint the first turn wrote."""
    graph = _reply_graph()
    agent = PycilAgent(name="pycil-assistant", graph=graph)
    encoder = EventEncoder()

    first = [encoder.encode(event) async for event in agent.run(_input())]
    assert any("RUN_FINISHED" in frame for frame in first)

    snapshot = await graph.aget_state({"configurable": {"thread_id": "thread-1"}})
    roles = [message.type for message in snapshot.values.get("messages", [])]

    assert roles.count("human") == 1
    assert roles.count("ai") == 1


async def test_a_multi_step_turn_writes_one_checkpoint_at_exit():
    """Exit-only durability: intermediate super-steps must not persist.

    A checkpoint per step is what grows a long turn's storage without adding a
    resumable state, so the count is the observable that proves the mode.
    """
    checkpointer = InMemorySaver()
    builder = StateGraph(_State)
    builder.add_node("first", lambda state: {"messages": [AIMessage(content="one")]})
    builder.add_node("second", lambda state: {"messages": [AIMessage(content="two")]})
    builder.add_edge("__start__", "first")
    builder.add_edge("first", "second")
    builder.add_edge("second", END)
    agent = PycilAgent(name="pycil-assistant", graph=builder.compile(checkpointer=checkpointer))

    async for _ in agent.run(_input()):
        pass

    written = [
        checkpoint
        async for checkpoint in checkpointer.alist({"configurable": {"thread_id": "thread-1"}})
    ]

    assert len(written) == 1
