"""Deck membership CRUD + ownership gating + content resolution via port."""

import uuid
from types import SimpleNamespace

import pytest

from pycil.account.schemas import CurrentUser
from pycil.account.user import User
from pycil.library import membership as service
from pycil.library import nodes as collection_service
from pycil.library.access import require_node_access
from pycil.library.models import Node, NodeType, Visibility
from pycil.platform.errors import ForbiddenError, NotFoundError

pytestmark = pytest.mark.asyncio


class FakeLexiClient:
    """Fake LexiClient — records get_senses calls; never touches a DB."""

    def __init__(self):
        self.get_senses_calls: list[list[int]] = []

    async def get_senses(self, sense_ids):
        self.get_senses_calls.append(sense_ids)
        return [
            SimpleNamespace(
                definition=f"def {sid}",
                tier="core",
                pos="noun",
                cefr_level="A1",
                sense_id=sid,
                examples=[],
                word=f"word{sid}",
                word_id=sid * 10,
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
    return CurrentUser(id=user.id, email=user.email)


async def test_create_and_add_sense(session):
    owner = await _seed_user(session)
    deck = await collection_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="My Deck"
    )
    assert deck.type == NodeType.DECK

    await service.add_sense(session, deck.id, 101)
    await service.add_sense(session, deck.id, 202)
    ids = await service.list_sense_ids(session, deck.id)
    assert ids == [101, 202]


async def test_add_sense_idempotent(session):
    owner = await _seed_user(session)
    deck = await collection_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="Deck"
    )
    await service.add_sense(session, deck.id, 5)
    await service.add_sense(session, deck.id, 5)  # dup
    ids = await service.list_sense_ids(session, deck.id)
    assert ids == [5]


async def test_remove_sense(session):
    owner = await _seed_user(session)
    deck = await collection_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="Deck"
    )
    await service.add_sense(session, deck.id, 7)
    await service.remove_sense(session, deck.id, 7)
    assert await service.list_sense_ids(session, deck.id) == []


async def test_require_node_access_owner_write(session):
    owner = await _seed_user(session)
    deck = await collection_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="Deck"
    )
    node = await require_node_access(session, deck.id, _cu(owner), write=True)
    assert node.id == deck.id


async def test_require_node_access_non_owner_write_forbidden(session):
    owner = await _seed_user(session)
    other = await _seed_user(session, email="other@x.co")
    deck = await collection_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="Deck"
    )
    with pytest.raises(ForbiddenError):
        await require_node_access(session, deck.id, _cu(other), write=True)


async def test_require_node_access_private_read_hidden_from_non_owner(session):
    owner = await _seed_user(session)
    other = await _seed_user(session, email="other@x.co")
    deck = await collection_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="Deck"
    )  # PRIVATE default
    # Non-owner read of a private node → 404 (existence not leaked).
    with pytest.raises(NotFoundError):
        await require_node_access(session, deck.id, _cu(other), write=False)


async def test_require_node_access_public_read_allowed(session):
    owner = await _seed_user(session)
    other = await _seed_user(session, email="other@x.co")
    deck = Node(author_id=owner.id, type=NodeType.DECK, name="Public", visibility=Visibility.PUBLIC)
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


async def test_deck_items_carry_the_headword_for_every_item(session):
    """A deck row renders the word, so no item may come back with a null one.

    pycil stores only an opaque sense_id, so the headword can only arrive from the
    Lexi read model. Before it existed on ``SenseView`` this listing was a column
    of definitions with nothing to label them.
    """
    from pycil.library.membership_api import deck_items

    owner = await _seed_user(session, "deck-items@x.co")
    deck = await collection_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="Deck"
    )
    await service.add_sense(session, deck.id, 11)
    await service.add_sense(session, deck.id, 22)

    items = await deck_items(deck.id, _cu(owner), session, FakeLexiClient())

    assert [item.sense_id for item in items] == [11, 22]
    assert all(item.word for item in items), "an item came back with no headword"
    assert [item.word for item in items] == ["word11", "word22"]
    assert [item.word_id for item in items] == [110, 220]


async def test_deck_items_listing_stays_lean(session):
    """The listing DTO must not grow into the full lexical record.

    ``SenseContent`` is also built inside the per-result loop in ``search_words``,
    which already issues one cross-boundary ``get_entry`` per result. The lexical
    record therefore lives on ``SenseDetailRead`` instead.

    The learning-state fields are the one sanctioned exception: they are populated
    only by ``deck_items``, from a single query for the whole deck, and stay None on
    the search path so its payload and query count are unchanged.
    """
    from pycil.lexicon.schemas import SenseContent

    lexical = {"sense_id", "definition", "tier", "pos", "cefr_level", "examples", "word", "word_id"}
    learning_state = {
        "mastery",
        "mastery_stage",
        "mastery_stage_name",
        "next_review_date",
        "review_count",
        "lapse_count",
        "status",
    }
    assert set(SenseContent.model_fields) == lexical | learning_state
    # No part of the full record leaked down from SenseDetailRead.
    assert not set(SenseContent.model_fields) & {
        "ipa_uk",
        "ipa_us",
        "forms",
        "references",
        "relations",
        "collocations",
        "guideword",
    }


async def test_search_results_carry_no_learning_state(session):
    """The keystroke path must not gain a per-user query or per-user fields."""
    from pycil.lexicon.views import sense_content

    view = (await FakeLexiClient().get_senses([1]))[0]
    content = sense_content(view)
    assert content.word == "word1"
    assert content.mastery is None
    assert content.mastery_stage is None
    assert content.status is None


async def test_deck_items_carry_the_callers_learning_state(session):
    """A deck row shows where the caller stands on each sense, in one query."""
    from datetime import UTC, datetime

    from pycil.library.membership_api import deck_items
    from pycil.study.models import SenseStatus, UserSenseStats

    owner = await _seed_user(session, "deck-state@x.co")
    deck = await collection_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="Deck"
    )
    await service.add_sense(session, deck.id, 11)
    await service.add_sense(session, deck.id, 22)
    due = datetime(2026, 8, 1, tzinfo=UTC)
    session.add(
        UserSenseStats(
            user_id=owner.id,
            sense_id=11,
            mastery=85,
            review_count=4,
            lapse_count=1,
            next_review_date=due,
            status=SenseStatus.scheduled,
        )
    )
    await session.commit()

    items = await deck_items(deck.id, _cu(owner), session, FakeLexiClient())
    studied = next(item for item in items if item.sense_id == 11)
    untouched = next(item for item in items if item.sense_id == 22)

    assert studied.mastery == 85
    assert studied.mastery_stage == 5
    assert studied.mastery_stage_name == "Fluent"
    assert studied.review_count == 4
    assert studied.lapse_count == 1
    assert studied.next_review_date == due
    assert studied.status == "scheduled"
    # Never studied stays NULL, not zero: "not started" and "scored zero" are
    # different things on a progress ramp.
    assert untouched.mastery is None
    assert untouched.review_count is None
    assert untouched.status is None


async def test_deck_items_expose_no_learning_state_to_anonymous(session):
    from pycil.library.membership_api import deck_items
    from pycil.library.models import Visibility
    from pycil.study.models import SenseStatus, UserSenseStats

    owner = await _seed_user(session, "deck-anon@x.co")
    deck = await collection_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="Deck"
    )
    deck.visibility = Visibility.PUBLIC
    await service.add_sense(session, deck.id, 11)
    session.add(
        UserSenseStats(
            user_id=owner.id, sense_id=11, mastery=85, review_count=4, status=SenseStatus.scheduled
        )
    )
    await session.commit()

    items = await deck_items(deck.id, None, session, FakeLexiClient())

    assert [item.sense_id for item in items] == [11]
    assert items[0].word == "word11"
    assert items[0].mastery is None, "another user's progress leaked to an anonymous read"
    assert items[0].status is None
