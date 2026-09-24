"""Coverage for hierarchy visibility, live references, and L1 versions."""

import pytest

from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ConflictError, ForbiddenError
from pycil.content.application import service as content_service
from pycil.hierarchy.application import cache, service, subtree
from pycil.hierarchy.application.access import require_node_access
from pycil.hierarchy.infra.models import NodeType, Visibility

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _current_user(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, email=user.email)


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


async def test_a_deck_edit_moves_the_membership_key_and_leaves_the_old_one_unread(session):
    """Membership is fenced by the deck's own generation, not by deletion.

    The old key is not removed — it expires on its own TTL. What makes the edit
    correct is that nothing reads it again once the generation has moved, which is
    also what lets a rollback leave cache and database consistent: there is no
    window where the current key is missing.
    """
    owner = await _user(session, "generation-owner@example.com")
    deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="generation deck"
    )
    await content_service.add_sense(session, deck.id, 71)
    old_generation = deck.content_generation
    await subtree.cached_sense_ids(session, deck.id, owner.id)

    await content_service.add_sense(session, deck.id, 72)
    await session.refresh(deck)

    assert deck.content_generation > old_generation
    # The read composes from the new generation, so the stale entry is irrelevant.
    assert await subtree.cached_sense_ids(session, deck.id, owner.id) == [71, 72]


async def test_a_visibility_change_denies_the_target_immediately(session):
    """Authorization is the database's, so it takes effect without any invalidation.

    This is the property the old design could not offer: a cached subtree *was* the
    authorization result, so a stale entry could serve senses a viewer had just lost
    access to. Here the deck set is re-authorized on every read, and the cache holds
    only membership for decks that already passed that check.
    """
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
    # Warm every cache the read touches, so the revocation below cannot be explained
    # by a cold cache.
    assert await subtree.cached_sense_ids(session, root.id, reader.id) == [73]

    await service.set_visibility(session, target, Visibility.PRIVATE)

    assert await subtree.resolve_sense_ids(session, root.id, reader.id) == []
    assert await subtree.cached_sense_ids(session, root.id, reader.id) == []


async def test_a_content_edit_does_not_touch_ancestors_or_inbound_references(session):
    """The fan-out that made one deck edit proportional to its readers is gone.

    A deck referenced by a folder: editing the deck must move only the deck's own
    generation. Nothing above it and nothing pointing at it changes, because neither
    depends on which senses the deck holds — they resolve that lazily on read.
    """
    owner = await _user(session, "fanout-owner@example.com")
    root = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="root"
    )
    deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="deck"
    )
    await service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="reference",
        parent_node_id=root.id,
        target_node_id=deck.id,
    )
    await session.refresh(root)
    await session.refresh(deck)
    root_before, deck_before = root.content_generation, deck.content_generation

    await content_service.add_sense(session, deck.id, 75)
    await session.refresh(root)
    await session.refresh(deck)

    assert deck.content_generation > deck_before, "the edited deck must move"
    assert root.content_generation == root_before, (
        "a content edit must not touch an ancestor's generation"
    )


async def test_subtree_read_falls_back_to_database_when_redis_fails(session, monkeypatch):
    owner = await _user(session, "redis-fallback-owner@example.com")
    deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="fallback deck"
    )
    await content_service.add_sense(session, deck.id, 74)

    async def unavailable(*args, **kwargs):
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(cache, "get_deck_senses", unavailable)
    monkeypatch.setattr(cache, "set_deck_senses", unavailable)

    assert await subtree.cached_sense_ids(session, deck.id, owner.id) == [74]
