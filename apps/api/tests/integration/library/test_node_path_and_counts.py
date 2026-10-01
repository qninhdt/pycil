"""Breadcrumb path and deck item counts on the node reads.

The path is the reason breadcrumbs cost one request instead of one per hop. It is
also an information-disclosure surface: an ancestor's NAME is readable content, so
a caller who cannot open a folder must not learn what it is called.
"""

import pytest

from pycil.account.schemas import CurrentUser
from pycil.account.user import User
from pycil.library import membership as content_service
from pycil.library import nodes as service
from pycil.library.models import NodeType, Visibility
from pycil.library.nodes_api import get_node, list_nodes
from pycil.library.tree import ancestor_chain

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _cu(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, email=user.email)


# --- path ------------------------------------------------------------------


async def test_path_is_root_first_and_ends_at_the_node(session):
    owner = await _user(session, "path-owner@example.com")
    root = await service.create_node(session, owner.id, node_type=NodeType.FOLDER, name="root")
    mid = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="mid", parent_node_id=root.id
    )
    deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="deck", parent_node_id=mid.id
    )

    read = await get_node(deck.id, _cu(owner), session)

    assert [hop.name for hop in read.path] == ["root", "mid", "deck"]
    assert [hop.type for hop in read.path] == [
        NodeType.FOLDER,
        NodeType.FOLDER,
        NodeType.DECK,
    ]
    assert read.path[-1].id == deck.id


async def test_a_root_node_has_a_single_hop_path(session):
    owner = await _user(session, "path-root@example.com")
    root = await service.create_node(session, owner.id, node_type=NodeType.FOLDER, name="solo")

    read = await get_node(root.id, _cu(owner), session)

    assert [hop.name for hop in read.path] == ["solo"]


async def test_path_truncates_at_an_unreadable_ancestor_and_leaks_no_name(session):
    # deck is inherited-public through `published`, but `secret` above it is not
    # readable by a stranger. The path must start at `published`, and the string
    # "secret" must not appear anywhere in the response.
    owner = await _user(session, "path-trunc-owner@example.com")
    stranger = await _user(session, "path-trunc-stranger@example.com")
    secret = await service.create_node(session, owner.id, node_type=NodeType.FOLDER, name="secret")
    published = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.FOLDER,
        name="published",
        parent_node_id=secret.id,
        visibility=Visibility.PUBLIC,
        confirm_subtree_publication=True,
    )
    deck = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.DECK,
        name="shared deck",
        parent_node_id=published.id,
    )

    stranger_read = await get_node(deck.id, _cu(stranger), session)
    anonymous_read = await get_node(deck.id, None, session)
    owner_read = await get_node(deck.id, _cu(owner), session)

    assert [hop.name for hop in stranger_read.path] == ["published", "shared deck"]
    assert [hop.name for hop in anonymous_read.path] == ["published", "shared deck"]
    assert "secret" not in str(stranger_read.model_dump())
    assert secret.id not in {hop.id for hop in stranger_read.path}
    # The owner still sees the whole chain.
    assert [hop.name for hop in owner_read.path] == ["secret", "published", "shared deck"]


async def test_path_hides_every_stacked_unreadable_ancestor(session):
    # Two private folders stacked above a published one. Truncating at the first
    # unreadable hop (root-first) would keep the middle private folder and leak its
    # name; the breadcrumb must expose only the readable suffix.
    owner = await _user(session, "path-stack-owner@example.com")
    stranger = await _user(session, "path-stack-stranger@example.com")
    secret_top = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="secret_top"
    )
    secret_mid = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.FOLDER,
        name="secret_mid",
        parent_node_id=secret_top.id,
    )
    published = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.FOLDER,
        name="published",
        parent_node_id=secret_mid.id,
        visibility=Visibility.PUBLIC,
        confirm_subtree_publication=True,
    )
    deck = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.DECK,
        name="shared deck",
        parent_node_id=published.id,
    )

    stranger_read = await get_node(deck.id, _cu(stranger), session)

    assert [hop.name for hop in stranger_read.path] == ["published", "shared deck"]
    dumped = str(stranger_read.model_dump())
    assert "secret_mid" not in dumped
    assert "secret_top" not in dumped


# --- item counts -----------------------------------------------------------


async def test_deck_rows_carry_item_count_and_folders_do_not(session):
    owner = await _user(session, "count-owner@example.com")
    root = await service.create_node(session, owner.id, node_type=NodeType.FOLDER, name="root")
    full = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="full", parent_node_id=root.id
    )
    empty = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="empty", parent_node_id=root.id
    )
    await content_service.add_sense(session, full.id, 1)
    await content_service.add_sense(session, full.id, 2)
    await content_service.add_sense(session, full.id, 3)

    # limit/cursor are FastAPI Query defaults, unresolved when the handler is
    # called directly, so they are passed explicitly.
    page = await list_nodes(_cu(owner), session, parent_node_id=root.id, cursor=None, limit=50)
    by_id = {item.id: item for item in page.items}

    assert by_id[full.id].item_count == 3
    # A deck with nothing in it reports 0, not None — absent from the aggregate is
    # still a known quantity.
    assert by_id[empty.id].item_count == 0

    roots = await list_nodes(_cu(owner), session, parent_node_id=None, cursor=None, limit=50)
    assert roots.items[0].item_count is None, "a FOLDER must not claim an item count"

    # And on the single-node read.
    assert (await get_node(full.id, _cu(owner), session)).item_count == 3
    assert (await get_node(root.id, _cu(owner), session)).item_count is None


async def test_list_rows_omit_the_path(session):
    # Documented asymmetry: one ancestor walk per row is the N+1 this rebuild
    # exists to remove, and the caller of a listing already knows the parent.
    owner = await _user(session, "count-nopath@example.com")
    root = await service.create_node(session, owner.id, node_type=NodeType.FOLDER, name="root")
    await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="deck", parent_node_id=root.id
    )

    # limit/cursor are FastAPI Query defaults, unresolved when the handler is
    # called directly, so they are passed explicitly.
    page = await list_nodes(_cu(owner), session, parent_node_id=root.id, cursor=None, limit=50)

    assert page.items[0].path is None


async def test_mutation_responses_omit_path_and_count(session):
    """The other four NodeRead producers deliberately populate neither field.

    A structural mutation invalidates the caller's node and list queries anyway, so
    the client refetches. Pinning it here is what stops the asymmetry from being
    silent — both fields are optional, so a producer that forgets them still
    compiles and still serialises.
    """
    from pycil.library.nodes_api import create_node, move_node, update_node, update_visibility
    from pycil.library.schemas import (
        NodeCreate,
        NodeMove,
        NodeUpdate,
        NodeVisibilityUpdate,
    )

    owner = await _user(session, "mutation-owner@example.com")
    folder = await service.create_node(session, owner.id, node_type=NodeType.FOLDER, name="folder")

    created = await create_node(NodeCreate(type=NodeType.DECK, name="deck"), _cu(owner), session)
    updated = await update_node(created.id, NodeUpdate(name="renamed"), _cu(owner), session)
    moved = await move_node(created.id, NodeMove(parent_node_id=folder.id), _cu(owner), session)
    visible = await update_visibility(
        created.id,
        NodeVisibilityUpdate(visibility=Visibility.PUBLIC),
        _cu(owner),
        session,
    )

    for response in (created, updated, moved, visible):
        assert response.path is None
        assert response.item_count is None


# --- the shared walk -------------------------------------------------------


async def test_ancestor_chain_terminates_on_a_cycle_without_raising(session):
    # A corrupted parent pointer must degrade, not 500: this walk runs inside every
    # structural mutation (generation bumping) and every node read (breadcrumbs).
    owner = await _user(session, "cycle-owner@example.com")
    a = await service.create_node(session, owner.id, node_type=NodeType.FOLDER, name="a")
    b = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="b", parent_node_id=a.id
    )
    # Force the cycle directly; the service layer refuses to create one.
    a.parent_node_id = b.id
    session.add(a)
    await session.commit()

    chain = await ancestor_chain(session, b.id)

    assert set(chain) == {a.id, b.id}
    assert len(chain) == 2


async def test_breadcrumb_still_names_the_node_on_a_cyclic_tree(session):
    # B11. The breadcrumb tells the user which screen they are on, so the one entry
    # it must never lose is the node itself. `_readable_path` reasons over a chain it
    # assumes ends at that node — the truncation walk, the `chain[start:]` slice and
    # the "last hop is already authorized" argument all rest on it. A corrupted
    # parent pointer must degrade to "just this node", never to a trail whose final
    # entry is some ancestor, which would read as "you are looking at that folder".
    owner = await _user(session, "breadcrumb-cycle@example.com")
    a = await service.create_node(session, owner.id, node_type=NodeType.FOLDER, name="a")
    b = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="b", parent_node_id=a.id
    )
    a.parent_node_id = b.id
    session.add(a)
    await session.commit()

    for node in (a, b):
        read = await get_node(node.id, _cu(owner), session)
        assert read.path, f"{node.name}: breadcrumb must never be empty"
        assert read.path[-1].id == node.id, (
            f"{node.name}: the breadcrumb's last entry must be the node itself, "
            f"got {read.path[-1].name!r}"
        )
