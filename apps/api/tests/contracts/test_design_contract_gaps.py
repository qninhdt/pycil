"""Known design gaps captured before their phased runtime fixes.

Every strict xfail is an executable specification. Later phases must make the
assertion pass and remove its marker; an unexpected pass therefore fails CI.
"""

import pytest

from pycil.auth.models import User
from pycil.common.errors import ConflictError, NotFoundError
from pycil.content import service as content_service
from pycil.content.models import DeckSense
from pycil.hierarchy import cache, service, subtree
from pycil.hierarchy.models import NodeType

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_private_foreign_reference_is_rejected(session):
    owner = await _user(session, "reference-owner@example.com")
    attacker = await _user(session, "reference-attacker@example.com")
    private_deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="private"
    )

    rejected = False
    try:
        await service.create_node(
            session,
            attacker.id,
            node_type=NodeType.REFERENCE,
            name="leaking-reference",
            target_node_id=private_deck.id,
        )
    except NotFoundError:
        rejected = True

    assert rejected


async def test_move_under_descendant_is_rejected(session):
    owner = await _user(session, "cycle-owner@example.com")
    root = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="root"
    )
    child = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.FOLDER,
        name="child",
        parent_node_id=root.id,
    )

    rejected = False
    try:
        await service.move_node(session, root, child.id)
    except ConflictError:
        rejected = True

    assert rejected


async def test_deck_cannot_be_used_as_parent(session):
    owner = await _user(session, "parent-shape-owner@example.com")
    deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="leaf"
    )

    rejected = False
    try:
        await service.create_node(
            session,
            owner.id,
            node_type=NodeType.DECK,
            name="invalid-child",
            parent_node_id=deck.id,
        )
    except ConflictError:
        rejected = True

    assert rejected


async def test_folder_cannot_own_senses(session):
    owner = await _user(session, "membership-owner@example.com")
    folder = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="folder"
    )

    rejected = False
    try:
        await content_service.add_sense(session, folder.id, 101)
    except ConflictError:
        rejected = True

    assert rejected


async def test_deleted_reference_target_contributes_no_senses(session):
    owner = await _user(session, "deleted-target-owner@example.com")
    root = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="root"
    )
    target = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="target"
    )
    session.add(DeckSense(node_id=target.id, sense_id=202, position=0))
    await session.commit()
    await service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="reference",
        parent_node_id=root.id,
        target_node_id=target.id,
    )
    await service.soft_delete_node(session, target)

    assert await subtree.resolve_sense_ids(session, root.id) == []


async def test_membership_change_invalidates_cached_sense_set(session):
    owner = await _user(session, "cache-owner@example.com")
    deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="cached"
    )
    generation = deck.structural_generation
    await cache.set_defset(deck.id, [], generation=generation)

    await content_service.add_sense(session, deck.id, 303)

    assert await cache.get_defset(deck.id, generation) is None


async def test_target_membership_invalidates_reference_root(session):
    owner = await _user(session, "reverse-cache-owner@example.com")
    root = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="root"
    )
    target = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="target"
    )
    await service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="reference",
        parent_node_id=root.id,
        target_node_id=target.id,
    )
    generation = root.structural_generation
    await cache.set_defset(root.id, [], generation=generation)

    await content_service.add_sense(session, target.id, 404)

    assert await cache.get_defset(root.id, generation) is None


async def test_cache_writes_are_bound_to_durable_structural_generations():
    import inspect

    from pycil.hierarchy.models import Node

    assert "structural_generation" in Node.model_fields
    assert "generation" in inspect.signature(cache.set_defset).parameters
