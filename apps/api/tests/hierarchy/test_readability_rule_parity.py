"""The readability rule has two implementations that must agree.

`access.can_read_node` walks the ancestry in Python, one `session.get` per hop.
`subtree._READABLE_DECKS_SQL` answers the same question for a whole set of nodes
in one recursive CTE. Both encode the same policy:

* a deleted node, or one with any deleted ancestor, is unreadable
* the author always reads their own node
* a PUBLIC node is readable by anyone
* otherwise a PUBLIC **folder** ancestor grants read access, but only through
  edges where every node has the **same owner**

Two implementations of one authorization rule is a silent-divergence risk, and the
failure is asymmetric: if the SQL is more permissive than the Python, a listing
leaks decks that opening individually would refuse. Nothing previously asserted
the two agree.

Each case below is chosen because it distinguishes the implementations — a
same-owner chain, a cross-owner chain, a deleted middle node, a public deck under
a private folder. A rule change that updates only one side turns one of these red.
"""

import pytest

from pycil.auth.models import User
from pycil.hierarchy.application import service, subtree
from pycil.hierarchy.application.access import can_read_node
from pycil.hierarchy.infra.models import Node, NodeType, Visibility

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _assert_agree(session, deck: Node, viewer_id) -> bool:
    """Both paths answer the same for one deck; returns their shared verdict."""
    await session.refresh(deck)
    python_says = await can_read_node(session, deck, viewer_id)
    sql_says = deck.id in set(await subtree.readable_deck_ids(session, [deck.id], viewer_id))
    assert python_says == sql_says, (
        f"can_read_node={python_says} but readable_deck_ids={sql_says} "
        f"for deck={deck.id} viewer={viewer_id}"
    )
    return python_says


async def test_owner_reads_their_own_private_deck(session):
    owner = await _user(session, "parity-owner@example.com")
    folder = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="private folder"
    )
    deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="deck", parent_node_id=folder.id
    )

    assert await _assert_agree(session, deck, owner.id) is True


async def test_a_stranger_cannot_read_a_private_deck(session):
    owner = await _user(session, "parity-owner-2@example.com")
    stranger = await _user(session, "parity-stranger@example.com")
    folder = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="private folder"
    )
    deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="deck", parent_node_id=folder.id
    )

    assert await _assert_agree(session, deck, stranger.id) is False
    assert await _assert_agree(session, deck, None) is False


async def test_a_public_folder_grants_inherited_read_through_same_owner_edges(session):
    owner = await _user(session, "parity-owner-3@example.com")
    reader = await _user(session, "parity-reader@example.com")
    folder = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.FOLDER,
        name="public folder",
        visibility=Visibility.PUBLIC,
        # Publishing a folder publishes its subtree, so the service demands the
        # caller say so explicitly. Not incidental here: inherited read access
        # through a public folder is the rule under test.
        confirm_subtree_publication=True,
    )
    deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="deck", parent_node_id=folder.id
    )

    assert await _assert_agree(session, deck, reader.id) is True


async def test_a_deleted_ancestor_makes_the_deck_unreadable(session):
    owner = await _user(session, "parity-owner-4@example.com")
    reader = await _user(session, "parity-reader-2@example.com")
    folder = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.FOLDER,
        name="public folder",
        visibility=Visibility.PUBLIC,
        # Publishing a folder publishes its subtree, so the service demands the
        # caller say so explicitly. Not incidental here: inherited read access
        # through a public folder is the rule under test.
        confirm_subtree_publication=True,
    )
    deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="deck", parent_node_id=folder.id
    )
    await service.soft_delete_node(session, folder)

    # Both must refuse. A path that only checks the node itself would say yes.
    assert await _assert_agree(session, deck, reader.id) is False
    assert await _assert_agree(session, deck, owner.id) is False


async def test_a_public_deck_is_readable_even_under_a_private_folder(session):
    owner = await _user(session, "parity-owner-5@example.com")
    reader = await _user(session, "parity-reader-3@example.com")
    folder = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="private folder"
    )
    deck = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.DECK,
        name="deck",
        parent_node_id=folder.id,
        visibility=Visibility.PUBLIC,
    )

    assert await _assert_agree(session, deck, reader.id) is True


async def test_a_root_level_private_deck_has_no_ancestor_to_inherit_from(session):
    """The no-parent case: the ancestry walk and the CTE both terminate at once."""
    owner = await _user(session, "parity-owner-6@example.com")
    stranger = await _user(session, "parity-stranger-2@example.com")
    deck = await service.create_node(session, owner.id, node_type=NodeType.DECK, name="loose")

    assert await _assert_agree(session, deck, owner.id) is True
    assert await _assert_agree(session, deck, stranger.id) is False


async def test_a_public_folder_does_not_grant_read_across_an_owner_change(session):
    """The `same_owner` half of the rule, which nothing else here exercises.

    A public folder owned by A, containing a deck owned by B: inheritance must NOT
    apply, or publishing your own folder would publish someone else's deck that
    happens to sit inside it. Dropping `same_owner` from the SQL leaves every other
    case in this file green, so without this the two implementations could diverge
    on precisely the condition that prevents a cross-account leak.
    """
    folder_owner = await _user(session, "parity-folder-owner@example.com")
    deck_owner = await _user(session, "parity-deck-owner@example.com")
    reader = await _user(session, "parity-reader-4@example.com")

    folder = await service.create_node(
        session,
        folder_owner.id,
        node_type=NodeType.FOLDER,
        name="public folder",
        visibility=Visibility.PUBLIC,
        confirm_subtree_publication=True,
    )
    # Written directly: the create path deliberately refuses a parent the caller
    # does not own, and the state under test is a tree that already crosses owners.
    deck = Node(
        author_id=deck_owner.id,
        type=NodeType.DECK,
        name="someone else's deck",
        parent_node_id=folder.id,
        visibility=Visibility.PRIVATE,
    )
    session.add(deck)
    await session.commit()
    await session.refresh(deck)

    assert await _assert_agree(session, deck, reader.id) is False
    assert await _assert_agree(session, deck, folder_owner.id) is False
    # The deck's own owner still reads it.
    assert await _assert_agree(session, deck, deck_owner.id) is True


async def test_an_anonymous_viewer_is_not_treated_as_the_owner(session):
    """`viewer_id IS NULL` must not short-circuit the owner comparison.

    `subtree.py` casts the viewer to text specifically so a NULL viewer does not
    compare equal to an author id. This is the case that would break if the cast
    were "simplified" away.
    """
    owner = await _user(session, "parity-owner-7@example.com")
    deck = await service.create_node(session, owner.id, node_type=NodeType.DECK, name="deck")

    assert await _assert_agree(session, deck, None) is False
