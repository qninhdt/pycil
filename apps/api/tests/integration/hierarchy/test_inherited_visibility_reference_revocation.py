"""External references must revoke immediately when inherited visibility changes."""

import pytest

from pycil.auth.models import User
from pycil.content.application import service as content_service
from pycil.hierarchy.application import service, subtree
from pycil.hierarchy.infra.models import NodeType, Visibility

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_hiding_public_ancestor_invalidates_descendant_reference_root(session):
    owner = await _user(session, "ancestor-owner@example.com")
    reader = await _user(session, "ancestor-reader@example.com")
    public_ancestor = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.FOLDER,
        name="published source",
        visibility=Visibility.PUBLIC,
        confirm_subtree_publication=True,
    )
    descendant_deck = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.DECK,
        name="inherited-public deck",
        parent_node_id=public_ancestor.id,
    )
    await content_service.add_sense(session, descendant_deck.id, 81)
    reference_root = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.FOLDER,
        name="unrelated published root",
        visibility=Visibility.PUBLIC,
        confirm_subtree_publication=True,
    )
    await service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="external reference",
        parent_node_id=reference_root.id,
        target_node_id=descendant_deck.id,
    )

    # Warm the read so the revocation below cannot be explained by a cold cache.
    assert await subtree.cached_sense_ids(session, reference_root.id, reader.id) == [81]

    await service.set_visibility(session, public_ancestor, Visibility.PRIVATE)

    # The reader loses access because the deck's own inherited readability changed,
    # and the read re-authorizes against the database every time — so this holds
    # even though nothing invalidated the reference root's cache entry.
    assert await subtree.cached_sense_ids(session, reference_root.id, reader.id) == []
    assert await subtree.resolve_sense_ids(session, reference_root.id, reader.id) == []


async def test_deleted_ancestor_makes_descendant_reference_target_unavailable(session):
    owner = await _user(session, "delete-owner@example.com")
    reference_root = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="reference root"
    )
    source_folder = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="source folder"
    )
    descendant_deck = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.DECK,
        name="nested target",
        parent_node_id=source_folder.id,
    )
    await content_service.add_sense(session, descendant_deck.id, 82)
    await service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="reference",
        parent_node_id=reference_root.id,
        target_node_id=descendant_deck.id,
    )

    assert await subtree.cached_sense_ids(session, reference_root.id, owner.id) == [82]
    await service.soft_delete_node(session, source_folder)

    assert await subtree.cached_sense_ids(session, reference_root.id, owner.id) == []



async def test_anonymous_viewer_is_not_privileged_over_a_signed_in_one(session):
    """A NULL viewer must never be treated as "skip the visibility check".

    The readable-deck predicate used to open with ``viewer_id IS NULL``, which
    short-circuited the whole OR to TRUE and returned every live reference target
    regardless of visibility or owner. The observable symptom was inverted
    authorization: signing OUT revealed a private deck that a signed-in reader was
    correctly denied. Anonymous must resolve through exactly the two paths
    ``can_read_node`` allows it, public or same-owner-inherited-public.
    """
    owner = await _user(session, "anon-bypass-owner@example.com")
    reader = await _user(session, "anon-bypass-reader@example.com")
    public_root = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.FOLDER,
        name="public root",
        visibility=Visibility.PUBLIC,
        confirm_subtree_publication=True,
    )
    private_deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="private deck"
    )
    await content_service.add_sense(session, private_deck.id, 4242)
    await service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="reference to a private deck",
        parent_node_id=public_root.id,
        target_node_id=private_deck.id,
    )

    assert await subtree.cached_sense_ids(session, public_root.id, reader.id) == []
    assert await subtree.cached_sense_ids(session, public_root.id, None) == []
    # The owner still reaches their own deck through the reference.
    assert await subtree.cached_sense_ids(session, public_root.id, owner.id) == [4242]


async def test_anonymous_still_reaches_a_genuinely_public_reference_target(session):
    """The tightening must not break the case references exist for."""
    owner = await _user(session, "anon-grant-owner@example.com")
    reference_root = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.FOLDER,
        name="reference root",
        visibility=Visibility.PUBLIC,
        confirm_subtree_publication=True,
    )
    public_deck = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.DECK,
        name="public deck",
        visibility=Visibility.PUBLIC,
    )
    await content_service.add_sense(session, public_deck.id, 4343)
    await service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="reference",
        parent_node_id=reference_root.id,
        target_node_id=public_deck.id,
    )

    assert await subtree.cached_sense_ids(session, reference_root.id, None) == [4343]
