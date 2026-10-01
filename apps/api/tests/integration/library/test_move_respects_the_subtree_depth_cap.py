"""A move must not be able to bury a subtree past the collection depth cap.

`_validate_parent` only checks the *parent's* own depth. That is not the property
the cap needs: a move can be perfectly legal at the destination and still push every
descendant of the moved node past the limit, because a short parent plus a tall
subtree is deep. `_validate_subtree_depth` is the check that sees it, and nothing
referenced `node_depth_exceeded` from a test — the guard was unverified.

The cases below are the two sides of the boundary: one step past the cap is
refused, and the deepest legal move still succeeds. Without the second, a check that
refused everything would pass.
"""

import uuid

import pytest

from pycil.account.user import User
from pycil.library import nodes as collection_service
from pycil.library.access import MAX_COLLECTION_DEPTH
from pycil.library.models import Node, NodeType
from pycil.platform.errors import ConflictError

pytestmark = pytest.mark.asyncio


async def _user(session) -> User:
    user = User(email=f"depth-{uuid.uuid4()}@example.test")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _chain(session, author_id, length: int) -> list[Node]:
    """A folder chain of exactly ``length`` nodes, built directly.

    Through `create_node` this would be the same rows at O(n²) queries, and the
    point of the fixture is the shape, not the path that made it.
    """
    nodes: list[Node] = []
    parent_id = None
    for index in range(length):
        node = Node(
            author_id=author_id,
            type=NodeType.FOLDER,
            name=f"level-{index}",
            parent_node_id=parent_id,
        )
        session.add(node)
        await session.flush()
        nodes.append(node)
        parent_id = node.id
    await session.commit()
    return nodes


async def _subtree(session, author_id, height: int) -> Node:
    """A movable node with ``height`` levels of descendants below it."""
    root = await collection_service.create_node(
        session, author_id, node_type=NodeType.FOLDER, name="moved root"
    )
    parent = root
    for index in range(height):
        parent = await collection_service.create_node(
            session,
            author_id,
            node_type=NodeType.FOLDER,
            name=f"descendant-{index}",
            parent_node_id=parent.id,
        )
    return root


async def test_a_tall_subtree_cannot_move_under_a_deep_parent(session):
    """The parent fits; the subtree does not. This is what the parent check misses."""
    owner = await _user(session)
    # A parent one level below the cap: legal to move under, by `_validate_parent`.
    chain = await _chain(session, owner.id, MAX_COLLECTION_DEPTH - 1)
    deep_parent = chain[-1]
    subtree = await _subtree(session, owner.id, height=2)

    with pytest.raises(ConflictError) as raised:
        await collection_service.move_node(session, subtree, deep_parent.id)
    assert raised.value.code == "node_depth_exceeded"


async def test_the_deepest_legal_move_still_succeeds(session):
    """The boundary is exclusive: a subtree that lands exactly at the cap is fine."""
    owner = await _user(session)
    chain = await _chain(session, owner.id, MAX_COLLECTION_DEPTH - 2)
    deep_parent = chain[-1]
    # Height 1 lands the deepest descendant exactly at the cap.
    subtree = await _subtree(session, owner.id, height=1)

    moved = await collection_service.move_node(session, subtree, deep_parent.id)
    assert moved.parent_node_id == deep_parent.id


async def test_a_shallow_move_is_unaffected(session):
    """The guard must not refuse ordinary moves near the root."""
    owner = await _user(session)
    chain = await _chain(session, owner.id, 3)
    subtree = await _subtree(session, owner.id, height=2)

    moved = await collection_service.move_node(session, subtree, chain[-1].id)
    assert moved.parent_node_id == chain[-1].id
