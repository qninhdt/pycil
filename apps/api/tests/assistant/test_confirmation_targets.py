"""What a confirmation request tells the learner about its target.

The confirmable tools are the destructive ones — move, publish, delete, and sense
removal — so the approval prompt is the last thing between a model's suggestion and
a learner losing a deck. A prompt naming only the tool asks them to authorise
`delete_node` against an opaque UUID, which is not informed consent.

These tests pin the two halves of that: the owned target's *name* is carried, and
nothing else from the tool arguments is.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from pycil.assistant.application import run_service
from pycil.assistant.domain.context import AssistantContext
from pycil.hierarchy.infra.models import Node, NodeType

from .conftest import create_run, create_thread, create_user

pytestmark = pytest.mark.asyncio


class InterruptingGraph:
    """A graph that proposes one sensitive tool call and then stops.

    Shaped to match what `_interrupt_tool` reads rather than mimicking LangGraph in
    full: an `__interrupt__` update carrying `action_requests`.
    """

    def __init__(self, tool: str, args: dict):
        self._tool = tool
        self._args = args

    async def astream(self, *args, **kwargs):
        del args, kwargs

        class Interrupt:
            def __init__(self, value):
                self.value = value

        yield (
            "updates",
            {
                "__interrupt__": [
                    Interrupt({"action_requests": [{"name": self._tool, "args": self._args}]})
                ]
            },
        )


async def _run_until_interrupt(engine, monkeypatch, owner, thread, run, tool, args):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(run_service, "async_session_factory", factory)

    return [
        event
        async for event in run_service.stream_run(
            InterruptingGraph(tool, args),
            run,
            AssistantContext(owner.id, owner.token_version),
            content="delete it",
        )
    ]


async def test_confirmation_names_the_owned_target_it_would_act_on(engine, session, monkeypatch):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    run = await create_run(session, thread.id, owner.id, __import__("uuid").uuid4())
    deck = Node(author_id=owner.id, type=NodeType.DECK, name="French verbs")
    session.add(deck)
    await session.commit()
    await session.refresh(deck)

    events = await _run_until_interrupt(
        engine,
        monkeypatch,
        owner,
        thread,
        run,
        "delete_node",
        {"node_id": str(deck.id)},
    )

    [confirmation] = [e for e in events if e.event_type == "confirmation_required"]
    payload = confirmation.sanitized_payload
    assert payload["tool"] == "delete_node"
    # The name, not the id. This is the difference between "delete this?" and
    # "delete French verbs?".
    assert payload["targets"] == {"node_id": "French verbs"}
    assert "action_id" in payload
    assert "expires_at" in payload


async def test_confirmation_payload_carries_no_ids_or_internal_fields(engine, session, monkeypatch):
    """The payload is rendered by the client, so it holds names and nothing else.

    The tool arguments also carry raw ids and the internal `_resource_generations`
    map used for staleness checks. Neither belongs in a payload the UI displays, and
    sending the whole argument dict would have been the easy mistake.
    """
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    run = await create_run(session, thread.id, owner.id, __import__("uuid").uuid4())
    folder = Node(author_id=owner.id, type=NodeType.FOLDER, name="Archive")
    session.add(folder)
    await session.commit()
    await session.refresh(folder)

    events = await _run_until_interrupt(
        engine,
        monkeypatch,
        owner,
        thread,
        run,
        "publish_node",
        {"node_id": str(folder.id)},
    )

    [confirmation] = [e for e in events if e.event_type == "confirmation_required"]
    payload = confirmation.sanitized_payload
    assert set(payload) == {"action_id", "tool", "expires_at", "targets"}
    assert "_resource_generations" not in payload
    assert str(folder.id) not in str(payload["targets"])


async def test_a_node_the_caller_does_not_own_is_not_named(engine, session, monkeypatch):
    """Ownership gates the name, as it already gated the generation read.

    An id the model invented, or one belonging to someone else, must not come back as
    a name — that would turn the approval card into a way to probe for other people's
    deck titles. The request still goes ahead: the tool itself enforces ownership on
    execution, so the card simply has nothing to name.
    """
    owner = await create_user(session)
    stranger = await create_user(session, "stranger@example.test")
    thread = await create_thread(session, owner.id)
    run = await create_run(session, thread.id, owner.id, __import__("uuid").uuid4())
    theirs = Node(author_id=stranger.id, type=NodeType.DECK, name="Their private deck")
    session.add(theirs)
    await session.commit()
    await session.refresh(theirs)

    events = await _run_until_interrupt(
        engine,
        monkeypatch,
        owner,
        thread,
        run,
        "delete_node",
        {"node_id": str(theirs.id)},
    )

    [confirmation] = [e for e in events if e.event_type == "confirmation_required"]
    assert confirmation.sanitized_payload["targets"] == {}
