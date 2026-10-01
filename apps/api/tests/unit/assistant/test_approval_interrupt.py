"""Approval pauses the graph, and only Approve performs the mutation.

Driven through the real AG-UI adapter and a real LangGraph agent, because the
interrupt/resume contract is what the web client depends on: an approval that
executed before the decision, or a Reject that still ran the tool, would both be
invisible to a unit test of the middleware config alone.
"""

import json

import pytest
from ag_ui.core import ResumeEntry, RunAgentInput, UserMessage
from ag_ui.encoder import EventEncoder
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from pycil.assistant.agent.adapter import PycilAgent
from pycil.assistant.turns.stream import _resume

pytestmark = pytest.mark.asyncio

THREAD_ID = "approval-thread"


class ScriptedModel(BaseChatModel):
    """A model that asks for the sensitive tool, then finishes.

    The provider is stubbed rather than mocked because the interrupt is produced
    by the real middleware from a real tool call; a fake at a lower level would
    not exercise the path the product runs.
    """

    replies: list = []
    index: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN003 - BaseChatModel API
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001
        reply = self.replies[min(self.index, len(self.replies) - 1)]
        self.index += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


def _build(mutations: list) -> PycilAgent:
    @tool
    def delete_node(node_id: str) -> str:
        """Delete a caller-owned node."""
        mutations.append(node_id)
        return "deleted"

    model = ScriptedModel(
        replies=[
            AIMessage(
                content="",
                tool_calls=[{"name": "delete_node", "args": {"node_id": "node-1"}, "id": "call-1"}],
            ),
            AIMessage(content="finished"),
        ]
    )
    graph = create_agent(
        model=model,
        tools=[delete_node],
        checkpointer=InMemorySaver(),
        middleware=[
            HumanInTheLoopMiddleware(
                interrupt_on={"delete_node": {"allowed_decisions": ["approve", "reject"]}}
            )
        ],
    )
    return PycilAgent(name="pycil-assistant", graph=graph)


def _start() -> RunAgentInput:
    return RunAgentInput(
        thread_id=THREAD_ID,
        run_id="run-1",
        messages=[UserMessage(id="m1", role="user", content="delete it")],
        tools=[],
        context=[],
        forwarded_props={},
    )


def _resume_input(interrupt_id: str, decision: dict) -> RunAgentInput:
    return RunAgentInput(
        thread_id=THREAD_ID,
        run_id="run-2",
        messages=[],
        tools=[],
        context=[],
        forwarded_props={},
        resume=[
            ResumeEntry(
                interrupt_id=interrupt_id,
                status="resolved",
                payload={"decisions": [decision]},
            )
        ],
    )


async def _interrupt_id(agent: PycilAgent, body: RunAgentInput) -> str:
    encoder = EventEncoder()
    frames = [encoder.encode(event) async for event in agent.run(body)]
    for frame in frames:
        if '"on_interrupt"' in frame:
            return json.loads(frame.split("data: ", 1)[1])["rawEvent"]["id"]
    raise AssertionError("the run produced no approval interrupt")


async def _resume_types(agent: PycilAgent, body: RunAgentInput) -> list[str]:
    return [str(getattr(event, "type", None)) async for event in agent.run(body)]


async def test_the_mutation_does_not_run_before_the_decision():
    """A paused run must not have executed the tool it is asking about."""
    mutations: list[str] = []
    agent = _build(mutations)

    interrupt_id = await _interrupt_id(agent, _start())

    assert interrupt_id
    assert mutations == []


async def test_reject_finishes_the_run_without_running_the_tool():
    mutations: list[str] = []
    agent = _build(mutations)
    interrupt_id = await _interrupt_id(agent, _start())

    types = await _resume_types(
        agent, _resume_input(interrupt_id, {"type": "reject", "message": "not now"})
    )

    assert mutations == []
    assert "EventType.RUN_FINISHED" in types
    assert "EventType.RUN_ERROR" not in types


async def test_approve_runs_the_tool_exactly_once():
    mutations: list[str] = []
    agent = _build(mutations)
    interrupt_id = await _interrupt_id(agent, _start())

    types = await _resume_types(agent, _resume_input(interrupt_id, {"type": "approve"}))

    assert mutations == ["node-1"]
    assert "EventType.RUN_FINISHED" in types


async def test_two_sensitive_actions_require_two_decisions():
    body = _resume_input("interrupt-1", {"type": "approve"})
    entry = body.resume[0]
    body = body.model_copy(
        update={
            "resume": [entry.model_copy(update={"payload": {"decisions": ["approve", "reject"]}})]
        }
    )
    translated, all_rejected = _resume(body, 2)
    assert translated.resume[0].payload == {"decisions": [{"type": "approve"}, {"type": "reject"}]}
    assert not all_rejected
