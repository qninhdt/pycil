"""Phase 2 coverage for hierarchy visibility, live references, and L1 versions."""

import pytest

from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ConflictError, ForbiddenError
from pycil.content import service as content_service
from pycil.hierarchy import cache, router, service, subtree
from pycil.hierarchy.access import require_node_access
from pycil.hierarchy.models import NodeType, Visibility

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _current_user(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, email=user.email, role=user.role)


async def test_public_folder_requires_explicit_publication_confirmation(session):
    owner = await _user(session, "publication-owner@example.com")

    with pytest.raises(ConflictError, match="folder_publication_requires_confirmation"):
        await service.create_node(
            session,
            owner.id,
            node_type=NodeType.FOLDER,
            name="public root",
            visibility=Visibility.PUBLIC,
        )


async def test_public_folder_grants_inherited_read_but_not_write(session):
    owner = await _user(session, "public-owner@example.com")
    reader = await _user(session, "public-reader@example.com")
    root = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.FOLDER,
        name="shared root",
        visibility=Visibility.PUBLIC,
        confirm_subtree_publication=True,
    )
    private_deck = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.DECK,
        name="inherited deck",
        parent_node_id=root.id,
    )

    assert (
        await require_node_access(session, private_deck.id, _current_user(reader), write=False)
    ).id == private_deck.id
    with pytest.raises(ForbiddenError):
        await require_node_access(session, private_deck.id, _current_user(reader), write=True)


async def test_public_root_hides_live_private_reference_target(session):
    owner = await _user(session, "reference-owner@example.com")
    reader = await _user(session, "reference-reader@example.com")
    root = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.FOLDER,
        name="shared root",
        visibility=Visibility.PUBLIC,
        confirm_subtree_publication=True,
    )
    target = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="private target"
    )
    await content_service.add_sense(session, target.id, 71)
    await service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="live reference",
        parent_node_id=root.id,
        target_node_id=target.id,
    )

    assert await subtree.resolve_sense_ids(session, root.id, reader.id) == []
    assert await subtree.resolve_sense_ids(session, root.id, owner.id) == [71]


async def test_generation_makes_stale_reference_cache_unreachable(session):
    owner = await _user(session, "generation-owner@example.com")
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
    old_generation = root.structural_generation
    await cache.set_defset(root.id, [999], generation=old_generation)

    await content_service.add_sense(session, target.id, 72)
    await session.refresh(root)
    await cache.set_defset(root.id, [999], generation=old_generation)

    assert root.structural_generation > old_generation
    assert await cache.get_defset(root.id, root.structural_generation) is None


async def test_visibility_change_invalidates_reverse_reference_roots(session):
    owner = await _user(session, "visibility-owner@example.com")
    reader = await _user(session, "visibility-reader@example.com")
    root = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.FOLDER,
        name="shared root",
        visibility=Visibility.PUBLIC,
        confirm_subtree_publication=True,
    )
    target = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.DECK,
        name="public target",
        visibility=Visibility.PUBLIC,
    )
    await content_service.add_sense(session, target.id, 73)
    await service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="reference",
        parent_node_id=root.id,
        target_node_id=target.id,
    )
    old_generation = root.structural_generation
    await cache.set_defset(root.id, [73], generation=old_generation, viewer_id=reader.id)

    await service.set_visibility(session, target, Visibility.PRIVATE)
    await session.refresh(root)

    assert root.structural_generation > old_generation
    assert await subtree.resolve_sense_ids(session, root.id, reader.id) == []
    assert (
        await cache.get_defset(root.id, root.structural_generation, viewer_id=reader.id)
        is None
    )


async def test_subtree_read_falls_back_to_database_when_redis_fails(session, monkeypatch):
    owner = await _user(session, "redis-fallback-owner@example.com")
    deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="fallback deck"
    )
    await content_service.add_sense(session, deck.id, 74)

    async def unavailable(*args, **kwargs):
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(cache, "get_defset", unavailable)
    monkeypatch.setattr(cache, "set_defset", unavailable)

    assert await router._defset(session, deck.id, owner.id) == [74]
