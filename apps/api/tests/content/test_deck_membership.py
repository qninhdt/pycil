"""Deck membership CRUD + ownership gating + content resolution via port."""

import uuid

import pytest

from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ForbiddenError, NotFoundError
from pycil.content import service
from pycil.hierarchy.access import require_node_access
from pycil.hierarchy.models import Node, NodeType, Visibility

pytestmark = pytest.mark.asyncio


class FakeLexiClient:
    """Fake LexiClient — records get_senses calls; never touches a DB."""

    def __init__(self):
        self.get_senses_calls: list[list[int]] = []

    async def get_senses(self, sense_ids):
        self.get_senses_calls.append(sense_ids)
        from lexi_ai.read_models import SenseView

        return [
            SenseView(
                definition=f"def {sid}",
                tier="core",
                pos="noun",
                cefr_level="A1",
                sense_id=sid,
            )
            for sid in sense_ids
        ]


async def _seed_user(session, email="owner@x.co") -> User:
    u = User(email=email)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


def _cu(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, email=user.email, role=user.role)


async def test_create_and_add_sense(session):
    owner = await _seed_user(session)
    deck = await service.create_deck(session, owner.id, "My Deck")
    assert deck.type == NodeType.DECK

    await service.add_sense(session, deck.id, 101)
    await service.add_sense(session, deck.id, 202)
    ids = await service.list_sense_ids(session, deck.id)
    assert ids == [101, 202]


async def test_add_sense_idempotent(session):
    owner = await _seed_user(session)
    deck = await service.create_deck(session, owner.id, "Deck")
    await service.add_sense(session, deck.id, 5)
    await service.add_sense(session, deck.id, 5)  # dup
    ids = await service.list_sense_ids(session, deck.id)
    assert ids == [5]


async def test_remove_sense(session):
    owner = await _seed_user(session)
    deck = await service.create_deck(session, owner.id, "Deck")
    await service.add_sense(session, deck.id, 7)
    await service.remove_sense(session, deck.id, 7)
    assert await service.list_sense_ids(session, deck.id) == []


async def test_require_node_access_owner_write(session):
    owner = await _seed_user(session)
    deck = await service.create_deck(session, owner.id, "Deck")
    node = await require_node_access(session, deck.id, _cu(owner), write=True)
    assert node.id == deck.id


async def test_require_node_access_non_owner_write_forbidden(session):
    owner = await _seed_user(session)
    other = await _seed_user(session, email="other@x.co")
    deck = await service.create_deck(session, owner.id, "Deck")
    with pytest.raises(ForbiddenError):
        await require_node_access(session, deck.id, _cu(other), write=True)


async def test_require_node_access_private_read_hidden_from_non_owner(session):
    owner = await _seed_user(session)
    other = await _seed_user(session, email="other@x.co")
    deck = await service.create_deck(session, owner.id, "Deck")  # PRIVATE default
    # Non-owner read of a private node → 404 (existence not leaked).
    with pytest.raises(NotFoundError):
        await require_node_access(session, deck.id, _cu(other), write=False)


async def test_require_node_access_public_read_allowed(session):
    owner = await _seed_user(session)
    other = await _seed_user(session, email="other@x.co")
    deck = Node(
        author_id=owner.id, type=NodeType.DECK, name="Public", visibility=Visibility.PUBLIC
    )
    session.add(deck)
    await session.commit()
    await session.refresh(deck)
    node = await require_node_access(session, deck.id, _cu(other), write=False)
    assert node.visibility == Visibility.PUBLIC


async def test_require_node_access_unknown_404(session):
    owner = await _seed_user(session)
    with pytest.raises(NotFoundError):
        await require_node_access(session, uuid.uuid4(), _cu(owner), write=False)


async def test_resolve_senses_uses_client_not_db(session):
    client = FakeLexiClient()
    views = await service.resolve_senses(client, [11, 22])
    assert client.get_senses_calls == [[11, 22]]
    assert [v.sense_id for v in views] == [11, 22]


async def test_resolve_senses_empty_shortcircuits(session):
    client = FakeLexiClient()
    assert await service.resolve_senses(client, []) == []
    assert client.get_senses_calls == []  # no client call on empty input


async def test_request_word_enqueues(session):
    owner = await _seed_user(session)

    class FakePool:
        def __init__(self):
            self.jobs = []

        async def enqueue_job(self, name, *args):
            self.jobs.append((name, args))

    pool = FakePool()
    await service.request_word(pool, owner.id, "serendipity")
    assert pool.jobs == [("generate_word", (str(owner.id), "serendipity"))]
