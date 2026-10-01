"""The adapter runs exit-only and keeps the actor's identity typed.

Both properties are injected through ``get_stream_kwargs``, which is the adapter's
own extension point. Neither is visible in the adapter's public signature, so a
change to the injection would silently revert to per-super-step checkpointing or
stringify the actor's UUID — and a stringified UUID breaks every tool that
compares it against an owner column.
"""

from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from pycil.assistant.agent.adapter import (
    DURABILITY,
    PycilAgent,
    checkpoint_thread_id,
)
from pycil.assistant.agent.context import AssistantContext


class _State(TypedDict):
    pass


def _compiled_graph():
    """The cheapest valid graph: the adapter inspects ``graph.nodes`` at construction."""
    builder = StateGraph(_State)
    builder.add_node("noop", lambda state: {})
    builder.add_edge("__start__", "noop")
    builder.add_edge("noop", END)
    return builder.compile()


def _agent() -> PycilAgent:
    return PycilAgent(name="pycil-assistant", graph=_compiled_graph())


def test_the_stream_requests_exit_only_checkpointing():
    """One checkpoint at exit, not one per super-step."""
    kwargs = _agent().get_stream_kwargs({"configurable": {}})

    assert kwargs["durability"] == DURABILITY == "exit"


def test_a_caller_supplied_durability_cannot_override_exit_only():
    """The kwarg is not part of the adapter's contract, so it is replaced, not merged."""
    kwargs = _agent().get_stream_kwargs({"configurable": {}}, durability="sync")

    assert kwargs["durability"] == "exit"


def test_the_actor_context_reaches_the_graph_as_a_typed_object():
    """The actor's UUID must stay a UUID: tools compare it against owner columns."""
    agent = _agent()
    owner_id = uuid4()
    agent.request_context = AssistantContext(user_id=owner_id)

    kwargs = agent.get_stream_kwargs({"configurable": {}})

    assert isinstance(kwargs["context"], AssistantContext)
    assert kwargs["context"].user_id == owner_id


def test_a_run_without_a_request_context_passes_none():
    """Building the kwargs before the router sets a context must not invent one."""
    kwargs = _agent().get_stream_kwargs({"configurable": {}})

    assert "context" not in kwargs


def test_the_checkpoint_key_is_namespaced_by_owner_and_thread():
    """A guessed thread id cannot collide with another learner's history."""
    owner_id, thread_id = uuid4(), uuid4()

    assert checkpoint_thread_id(owner_id, thread_id) == f"assistant:{owner_id}:{thread_id}"
    assert checkpoint_thread_id(owner_id, thread_id) != checkpoint_thread_id(uuid4(), thread_id)
