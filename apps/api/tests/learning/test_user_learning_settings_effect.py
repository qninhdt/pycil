"""Session settings must actually shape a session, and must belong to the learner.

Two defects are pinned here.

The first is historical: the PATCH wrote ``new_per_batch`` / ``review_per_batch``
into ``deck_attributes.settings`` while the planner read
``target_words_per_session`` / ``max_questions_per_round``. The key sets never
intersected, so every session silently used the policy defaults. A round-trip test
on the endpoint could not catch it, because the value it wrote was the value it read
back. So every assertion below reaches the value through the planner's own resolver
rather than through the DTO that wrote it.

The second is why the settings moved to the user: they used to live on a deck, and
only a deck. Starting a session on a folder read no settings row at all, so the
learner's configured session length applied on some screens and not others. The
folder test below is the one that would have caught that.
"""

import random
import uuid
from datetime import UTC, datetime

import fakeredis.aioredis as fake_aioredis
import pytest

from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.content import service as content_service
from pycil.hierarchy import service as hierarchy_service
from pycil.hierarchy.models import NodeType
from pycil.learning import planning, session_store
from pycil.learning.policy import (
    DEFAULT_MAX_QUESTIONS_PER_ROUND,
    DEFAULT_TARGET_WORDS_PER_SESSION,
)
from pycil.learning.router import get_learning_settings, update_learning_settings
from pycil.learning.schemas import LearningSettingsUpdate

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _cu(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, email=user.email)


async def _deck_with_senses(session, author_id, count: int, parent_node_id=None):
    deck = await hierarchy_service.create_node(
        session,
        author_id,
        node_type=NodeType.DECK,
        name="deck",
        parent_node_id=parent_node_id,
    )
    for sense_id in range(1, count + 1):
        await content_service.add_sense(session, deck.id, sense_id)
    return deck


async def _save(session, user: User, *, words: int, per_round: int) -> None:
    await update_learning_settings(
        LearningSettingsUpdate(
            targetWordsPerSession=words, maxQuestionsPerRound=per_round
        ),
        _cu(user),
        session,
    )


async def test_written_settings_are_the_ones_the_planner_reads(session):
    owner = await _user(session, "settings-effect@example.com")
    await _save(session, owner, words=4, per_round=3)

    # Through the planner's resolver, not the DTO that wrote it: that is the whole
    # point of this file.
    effective = await planning.settings_for_user(session, owner.id)

    assert effective.target_words_per_session == 4
    assert effective.max_questions_per_round == 3


async def test_target_words_caps_the_admitted_set(session):
    """The measurable consequence: fewer senses enter the session."""
    owner = await _user(session, "settings-admit@example.com")
    deck = await _deck_with_senses(session, owner.id, 20)
    now = datetime.now(UTC)

    default_plan = await planning.plan_session(
        session,
        owner.id,
        deck.id,
        now,
        await planning.settings_for_user(session, owner.id),
        random.Random(1),
    )
    assert len(default_plan.admitted) == DEFAULT_TARGET_WORDS_PER_SESSION

    await _save(session, owner, words=4, per_round=3)
    tuned_plan = await planning.plan_session(
        session,
        owner.id,
        deck.id,
        now,
        await planning.settings_for_user(session, owner.id),
        random.Random(1),
    )

    assert len(tuned_plan.admitted) == 4


async def test_settings_apply_to_a_folder_session_too(session):
    """The reason these moved off the deck.

    A folder has no settings row and never will, so reading settings from the node
    meant a folder session silently used the policy defaults while a deck session
    used the configured value. The same learner got two different session lengths
    depending on which screen they started from.
    """
    owner = await _user(session, "settings-folder-scope@example.com")
    folder = await hierarchy_service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="folder"
    )
    await _deck_with_senses(session, owner.id, 20, parent_node_id=folder.id)
    await _save(session, owner, words=4, per_round=3)

    plan = await planning.plan_session(
        session,
        owner.id,
        folder.id,
        datetime.now(UTC),
        await planning.settings_for_user(session, owner.id),
        random.Random(1),
    )

    assert len(plan.admitted) == 4


async def test_settings_are_per_user_not_shared(session):
    """One learner's choice must not move another's session."""
    first = await _user(session, "settings-mine@example.com")
    second = await _user(session, "settings-yours@example.com")

    await _save(session, first, words=4, per_round=3)

    mine = await planning.settings_for_user(session, first.id)
    theirs = await planning.settings_for_user(session, second.id)

    assert mine.target_words_per_session == 4
    assert theirs.target_words_per_session == DEFAULT_TARGET_WORDS_PER_SESSION


async def test_max_questions_per_round_reaches_the_session_meta(session):
    """The per-round cap is what the round scheduler enforces, so it has to land on
    the session, not just in the settings row."""
    owner = await _user(session, "settings-round@example.com")
    deck = await _deck_with_senses(session, owner.id, 20)
    await _save(session, owner, words=4, per_round=3)
    effective = await planning.settings_for_user(session, owner.id)

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


async def test_no_row_resolves_to_policy_defaults(session):
    """An absent row is the normal state, not a missing one.

    Signing up writes nothing, so most learners have no row. The read must report
    what the next session will actually use rather than an empty object every client
    would have to interpret.
    """
    owner = await _user(session, "settings-none@example.com")

    effective = await planning.settings_for_user(session, owner.id)
    assert effective.target_words_per_session == DEFAULT_TARGET_WORDS_PER_SESSION
    assert effective.max_questions_per_round == DEFAULT_MAX_QUESTIONS_PER_ROUND

    read = await get_learning_settings(_cu(owner), session)
    assert read.target_words_per_session == DEFAULT_TARGET_WORDS_PER_SESSION
    assert read.max_questions_per_round == DEFAULT_MAX_QUESTIONS_PER_ROUND


async def test_second_write_updates_rather_than_failing(session):
    """The row is absent until someone saves, so the write is an upsert.

    A read-then-branch would take the insert path twice for two concurrent first
    saves and the second would fail on the primary key. Saving twice in sequence is
    the cheap version of that check.
    """
    owner = await _user(session, "settings-upsert@example.com")

    await _save(session, owner, words=4, per_round=3)
    await _save(session, owner, words=7, per_round=5)

    effective = await planning.settings_for_user(session, owner.id)
    assert effective.target_words_per_session == 7
    assert effective.max_questions_per_round == 5


@pytest.mark.parametrize(
    ("words", "per_round"),
    [(0, 8), (10, 0), (-1, 8), (101, 8), (10, 101)],
)
async def test_out_of_range_values_are_refused(session, words, per_round):
    """The planner divides its work by both numbers, so a zero would build a session
    with nothing in it. Refused at the DTO, and again by a CHECK constraint."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        LearningSettingsUpdate(
            targetWordsPerSession=words, maxQuestionsPerRound=per_round
        )
