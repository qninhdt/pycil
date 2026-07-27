"""Deck settings must actually shape a session.

They never did. The PATCH wrote ``new_per_batch`` / ``review_per_batch`` into
``deck_attributes.settings`` while ``planning.settings_from_deck`` read
``target_words_per_session`` / ``max_questions_per_round``. The key sets never
intersected, so every session silently used the policy defaults no matter what the
learner configured. A round-trip test on the endpoint alone could not catch that —
it passed, because the value it wrote was the value it read back.
"""

import pytest

from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.content import service as content_service
from pycil.hierarchy import service as hierarchy_service
from pycil.hierarchy.models import DeckAttributes, NodeType
from pycil.hierarchy.router import get_deck_settings, update_deck_settings
from pycil.hierarchy.schemas import DeckSettingsUpdate
from pycil.learning import planning
from pycil.learning.policy import (
    DEFAULT_MAX_QUESTIONS_PER_ROUND,
    DEFAULT_TARGET_WORDS_PER_SESSION,
)

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _cu(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, email=user.email)


async def _deck_with_senses(session, author_id, count: int):
    deck = await hierarchy_service.create_node(
        session, author_id, node_type=NodeType.DECK, name="deck"
    )
    for sense_id in range(1, count + 1):
        await content_service.add_sense(session, deck.id, sense_id)
    return deck


async def test_written_settings_are_the_ones_the_planner_reads(session):
    owner = await _user(session, "settings-effect@example.com")
    deck = await _deck_with_senses(session, owner.id, 20)

    await update_deck_settings(
        deck.id,
        DeckSettingsUpdate(targetWordsPerSession=4, maxQuestionsPerRound=3),
        _cu(owner),
        session,
    )

    # Read through the planner's own resolver, not through the DTO that wrote it.
    attributes = await session.get(DeckAttributes, deck.id)
    effective = planning.settings_from_deck(attributes.settings)
    assert effective.target_words_per_session == 4
    assert effective.max_questions_per_round == 3


async def test_target_words_caps_the_admitted_set(session):
    """The measurable consequence: fewer senses enter the session."""
    import random
    from datetime import UTC, datetime

    owner = await _user(session, "settings-admit@example.com")
    deck = await _deck_with_senses(session, owner.id, 20)
    now = datetime.now(UTC)

    default_plan = await planning.plan_session(
        session,
        owner.id,
        deck.id,
        now,
        planning.settings_from_deck(None),
        random.Random(1),
    )
    assert len(default_plan.admitted) == DEFAULT_TARGET_WORDS_PER_SESSION

    await update_deck_settings(
        deck.id,
        DeckSettingsUpdate(targetWordsPerSession=4, maxQuestionsPerRound=3),
        _cu(owner),
        session,
    )
    attributes = await session.get(DeckAttributes, deck.id)
    tuned_plan = await planning.plan_session(
        session,
        owner.id,
        deck.id,
        now,
        planning.settings_from_deck(attributes.settings),
        random.Random(1),
    )

    assert len(tuned_plan.admitted) == 4


async def test_max_questions_per_round_reaches_the_session_meta(session):
    """The per-round cap is what the round scheduler enforces, so it has to land
    on the session, not just in the settings row."""
    import uuid

    import fakeredis.aioredis as fake_aioredis

    from pycil.learning import session_store

    owner = await _user(session, "settings-round@example.com")
    deck = await _deck_with_senses(session, owner.id, 20)
    await update_deck_settings(
        deck.id,
        DeckSettingsUpdate(targetWordsPerSession=4, maxQuestionsPerRound=3),
        _cu(owner),
        session,
    )
    attributes = await session.get(DeckAttributes, deck.id)
    effective = planning.settings_from_deck(attributes.settings)

    redis = fake_aioredis.FakeRedis(decode_responses=True)
    sid = uuid.uuid4().hex
    meta = await session_store.create(
        redis,
        sid,
        owner_id=owner.id,
        node_id=deck.id,
        scope_generation=1,
        target_words=effective.target_words_per_session,
        max_per_round=effective.max_questions_per_round,
        admitted=[],
    )

    assert meta.max_per_round == 3
    assert (await session_store.get_meta(redis, sid)).max_per_round == 3


async def test_a_deck_holding_only_legacy_keys_resolves_to_policy_defaults(session):
    """The old keys were inert, so there is no value to migrate — but they must not
    resolve to something surprising either."""
    owner = await _user(session, "settings-legacy@example.com")
    deck = await _deck_with_senses(session, owner.id, 3)
    # create_node already made the attributes row, so seed the legacy shape onto it.
    attributes = await session.get(DeckAttributes, deck.id)
    attributes.settings = {"new_per_batch": 7, "review_per_batch": 13}
    await session.commit()

    effective = planning.settings_from_deck(attributes.settings)
    assert effective.target_words_per_session == DEFAULT_TARGET_WORDS_PER_SESSION
    assert effective.max_questions_per_round == DEFAULT_MAX_QUESTIONS_PER_ROUND

    # And the read endpoint reports those effective defaults rather than the dead
    # keys or an empty object the client would have to interpret.
    read = await get_deck_settings(deck.id, _cu(owner), session)
    assert read.target_words_per_session == DEFAULT_TARGET_WORDS_PER_SESSION
    assert read.max_questions_per_round == DEFAULT_MAX_QUESTIONS_PER_ROUND


async def test_settings_read_reports_defaults_when_no_row_exists(session):
    owner = await _user(session, "settings-none@example.com")
    deck = await _deck_with_senses(session, owner.id, 1)

    read = await get_deck_settings(deck.id, _cu(owner), session)

    assert read.target_words_per_session == DEFAULT_TARGET_WORDS_PER_SESSION
    assert read.max_questions_per_round == DEFAULT_MAX_QUESTIONS_PER_ROUND


async def test_legacy_keys_are_replaced_not_merged(session):
    """A write must leave no dead keys behind to confuse a later reader."""
    owner = await _user(session, "settings-replace@example.com")
    deck = await _deck_with_senses(session, owner.id, 1)
    legacy = await session.get(DeckAttributes, deck.id)
    legacy.settings = {"new_per_batch": 7, "review_per_batch": 13}
    await session.commit()

    await update_deck_settings(
        deck.id,
        DeckSettingsUpdate(targetWordsPerSession=5, maxQuestionsPerRound=6),
        _cu(owner),
        session,
    )

    attributes = await session.get(DeckAttributes, deck.id)
    assert attributes.settings == {
        "target_words_per_session": 5,
        "max_questions_per_round": 6,
    }


async def test_non_deck_settings_write_is_rejected(session):
    from pycil.common.errors import ConflictError

    owner = await _user(session, "settings-folder@example.com")
    folder = await hierarchy_service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="folder"
    )

    with pytest.raises(ConflictError, match="node_is_not_deck"):
        await update_deck_settings(
            folder.id,
            DeckSettingsUpdate(targetWordsPerSession=5, maxQuestionsPerRound=6),
            _cu(owner),
            session,
        )
    with pytest.raises(ConflictError, match="node_is_not_deck"):
        await get_deck_settings(folder.id, _cu(owner), session)
