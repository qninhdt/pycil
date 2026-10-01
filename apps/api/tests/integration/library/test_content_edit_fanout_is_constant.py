"""A popular deck's content edit must not scale with how many people reference it.

The redesign's central claim is that adding a sense to a deck costs the same
whether one folder references it or ten thousand do. The old implementation walked
ancestors and inbound references on every content edit, so the write count grew with
the reference count — and the plan calls that out as the failure to eliminate.

This measures writes rather than asserting a wall-clock number: a timing assertion
on a shared CI machine is noise, while "how many rows did this statement touch" is
the actual property.

The bound is constant, not one: the edit moves the deck's `content_generation` and
the `structural_generation` of the deck and its ancestors, one statement each. What
must not grow is the count as referrers are added, and the assertions below pin both
halves — the write count and the referrers' own generations staying put.
"""

import pytest
from sqlalchemy import event

from pycil.account.user import User
from pycil.library import membership as content_service
from pycil.library import nodes as collection_service
from pycil.library.models import NodeType, Visibility

pytestmark = pytest.mark.asyncio

#: Enough references that a fan-out implementation would be unmistakable. Kept
#: modest so the test stays fast; the property is linear-vs-constant, not the
#: absolute count.
REFERENCE_COUNT = 200


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


class _Counter:
    """Counts UPDATE statements that touch the nodes table."""

    def __init__(self, engine):
        self.engine = engine
        self.updates = 0
        self._listening = False

    def __enter__(self):
        @event.listens_for(self.engine.sync_engine, "before_cursor_execute")
        def _before(conn, cursor, statement, parameters, context, executemany):
            normalized = " ".join(statement.split()).lower()
            if normalized.startswith("update nodes"):
                self.updates += 1

        self._listener = _before
        return self

    def __exit__(self, *exc):
        event.remove(self.engine.sync_engine, "before_cursor_execute", self._listener)
        return False


#: The two generations a content edit moves, one statement each: the deck's own
#: `content_generation` (which fences its cached membership) and the
#: `structural_generation` of the deck and its ancestors (which fences a live
#: session's scope). Both are bounded by the tree above the deck, so neither grows
#: with how many folders reference it.
EXPECTED_NODE_UPDATES = 2


async def test_a_content_edit_touches_one_generation_regardless_of_reference_count(session, engine):
    owner = await _user(session, "fanout-measure@example.com")
    deck = await collection_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="popular deck"
    )

    # Many published folders each holding a reference to the one deck.
    referrers: list = []
    for index in range(REFERENCE_COUNT):
        root = await collection_service.create_node(
            session,
            owner.id,
            node_type=NodeType.FOLDER,
            name=f"referrer {index}",
            visibility=Visibility.PUBLIC,
            confirm_subtree_publication=True,
        )
        referrers.append(root)
        await collection_service.create_node(
            session,
            owner.id,
            node_type=NodeType.REFERENCE,
            name=f"reference {index}",
            parent_node_id=root.id,
            target_node_id=deck.id,
        )
    await session.commit()
    await session.refresh(deck)
    before = deck.content_generation
    referrer_generations = {root.id: root.structural_generation for root in referrers}

    with _Counter(engine) as counter:
        await content_service.add_sense(session, deck.id, 501)

    await session.refresh(deck)
    assert deck.content_generation == before + 1, "the deck's own generation moves once"
    assert counter.updates == EXPECTED_NODE_UPDATES, (
        f"a content edit issued {counter.updates} node updates; it must touch only "
        f"the edited deck and the tree above it, not the {REFERENCE_COUNT} folders "
        f"that reference it"
    )
    # The referrers are the fan-out the redesign removed: pointing at a deck is not
    # the same as containing it, so a change to the target leaves them alone.
    for root in referrers:
        await session.refresh(root)
        assert root.structural_generation == referrer_generations[root.id], (
            "a folder that merely references the edited deck had its generation moved"
        )


async def test_reading_a_heavily_referenced_deck_still_returns_its_senses(session):
    """The O(1) edit must not have been bought by breaking the read."""
    owner = await _user(session, "fanout-read@example.com")
    deck = await collection_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="read deck"
    )
    root = await collection_service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="read root"
    )
    await collection_service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="read reference",
        parent_node_id=root.id,
        target_node_id=deck.id,
    )
    await content_service.add_sense(session, deck.id, 601)
    await content_service.add_sense(session, deck.id, 602)

    from pycil.library import scope as subtree

    assert await subtree.cached_sense_ids(session, root.id, owner.id) == [601, 602]
    # And through a reference, which is how the popular deck is actually reached.
    assert await subtree.cached_sense_ids(session, deck.id, owner.id) == [601, 602]
