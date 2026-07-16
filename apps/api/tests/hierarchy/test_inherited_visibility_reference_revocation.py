"""External references must revoke immediately when inherited visibility changes."""

import pytest

from pycil.auth.models import User
from pycil.content import service as content_service
from pycil.hierarchy import router, service
from pycil.hierarchy.models import NodeType, Visibility

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

    assert await router._defset(session, reference_root.id, reader.id) == [81]
    old_generation = reference_root.structural_generation

    await service.set_visibility(session, public_ancestor, Visibility.PRIVATE)
    await session.refresh(reference_root)

    assert reference_root.structural_generation > old_generation
    assert await router._defset(session, reference_root.id, reader.id) == []


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

    assert await router._defset(session, reference_root.id, owner.id) == [82]
    await service.soft_delete_node(session, source_folder)

    assert await router._defset(session, reference_root.id, owner.id) == []
