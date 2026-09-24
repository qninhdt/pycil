"""The assistant listing pages through the one id-keyset scheme over nodes."""

from uuid import UUID

import pytest

from pycil.assistant.application import hierarchy_facade
from pycil.hierarchy.application import reads
from pycil.hierarchy.infra.models import Node, NodeType

from .conftest import create_user

pytestmark = pytest.mark.asyncio


async def _folder_with_children(session, owner_id: int, count: int) -> tuple[Node, list[Node]]:
    folder = Node(author_id=owner_id, type=NodeType.FOLDER, name="root")
    session.add(folder)
    await session.commit()
    await session.refresh(folder)
    children = []
    for index in range(count):
        node = Node(
            author_id=owner_id,
            type=NodeType.DECK,
            name=f"deck-{index}",
            parent_node_id=folder.id,
        )
        session.add(node)
        children.append(node)
    await session.commit()
    for node in children:
        await session.refresh(node)
    return folder, children


async def test_listing_walks_every_child_once_in_id_order_via_the_shared_helper(session):
    """Tool page == route helper page; cursors walk the collection without gaps or repeats."""
    owner = await create_user(session)
    folder, children = await _folder_with_children(session, owner.id, 5)

    page = await hierarchy_facade.list_nodes(session, owner.id, folder.id, limit=3)
    helper_page, helper_cursor = await reads.owned_children_page(
        session, owner.id, folder.id, cursor=None, limit=3
    )

    assert [item["id"] for item in page["items"]] == [str(node.id) for node in helper_page]
    assert page["next_cursor"] == helper_cursor == str(sorted(children, key=lambda n: n.id)[2].id)

    seen = [item["id"] for item in page["items"]]
    while page["next_cursor"] is not None:
        page = await hierarchy_facade.list_nodes(
            session, owner.id, folder.id, limit=3, cursor=UUID(page["next_cursor"])
        )
        seen.extend(item["id"] for item in page["items"])

    assert seen == [str(node.id) for node in sorted(children, key=lambda n: n.id)]


async def test_foreign_cursor_scans_the_caller_scope_instead_of_erroring(session):
    """A cursor id outside the collection cannot widen visibility.

    The owner predicate always applies, so a foreign id only shifts where the
    caller's own scan resumes — the rows after it, still exclusively theirs.
    """
    owner = await create_user(session)
    intruder = await create_user(session, "listing-intruder@example.test")
    intruder_deck = Node(author_id=intruder.id, type=NodeType.DECK, name="foreign")
    session.add(intruder_deck)
    await session.commit()
    await session.refresh(intruder_deck)

    folder, children = await _folder_with_children(session, owner.id, 3)

    page = await hierarchy_facade.list_nodes(
        session, owner.id, folder.id, limit=10, cursor=intruder_deck.id
    )

    expected = [
        str(node.id) for node in sorted(children, key=lambda n: n.id) if node.id > intruder_deck.id
    ]
    assert [item["id"] for item in page["items"]] == expected
    assert str(intruder_deck.id) not in {item["id"] for item in page["items"]}


async def test_exhausted_page_reports_no_next_cursor(session):
    owner = await create_user(session)
    folder, children = await _folder_with_children(session, owner.id, 2)

    page = await hierarchy_facade.list_nodes(
        session, owner.id, folder.id, limit=len(children) + 5
    )

    assert len(page["items"]) == len(children)
    assert page["next_cursor"] is None
