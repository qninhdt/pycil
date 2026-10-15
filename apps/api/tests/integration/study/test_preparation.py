from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from pycil.account.models import User
from pycil.account.plans import Plan
from pycil.app.config import load_config
from pycil.app.http import Problem
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.library.models import NodeType
from pycil.library.nodes import create_node
from pycil.library.schemas import NodeCreate
from pycil.study import preparation
from pycil.study.artifacts.schemas import Artifact
from pycil.study.artifacts.storage import append
from pycil.study.enums import (
    LearningState,
    QuestionArtifactType,
    QuestionType,
    ResponseFormat,
    Selection,
)
from pycil.study.models import ReviewReceipt, UserSense
from pycil.vocabulary.enums import PartOfSpeech, Tier
from pycil.vocabulary.models import Definition, Sense
from tests.support.account import account
from tests.support.clock import frozen_datetime
from tests.support.vocabulary import neutral_word


class UnusedProvider:
    async def complete(self, *args, **options):
        pytest.fail("sufficient banks must not invoke a provider")


@pytest.fixture
async def prepared_library(database, monkeypatch):
    config = load_config()
    now = datetime(2026, 10, 13, 12, tzinfo=UTC)
    monkeypatch.setattr(preparation, "datetime", frozen_datetime(now))
    user, _ = await account(database.sessions)
    word_id, first_id = await neutral_word(database.sessions)
    async with database.sessions() as session, session.begin():
        extra = [Sense(word_id=word_id, pos=PartOfSpeech.NOUN, tier=Tier.CORE) for _ in range(3)]
        session.add_all(extra)
        await session.flush()
        ids = [first_id, *(sense.id for sense in extra)]
        for sense in extra:
            session.add(Definition(sense_id=sense.id, content="an institution holding deposits"))
        current = await session.get(User, user.id)
        current.settings = {
            "learning": {
                "question_types": [QuestionType.WORD_TO_DEFINITION],
                "formats": [ResponseFormat.SHORT_ANSWER],
                "questions_per_sense": 1,
                "max_sense_count": 4,
            }
        }
        for sense_id, due_at in [
            (ids[1], now),
            (ids[2], now - timedelta(days=1)),
            (ids[3], now + timedelta(days=1)),
        ]:
            session.add(
                UserSense(
                    user_id=user.id,
                    sense_id=sense_id,
                    stability=1,
                    difficulty=5,
                    elo=config.product.study.mastery.initial_elo,
                    last_exposure_at=now - timedelta(days=2),
                    due_at=due_at,
                    review_count=1,
                    lapse_count=0,
                )
            )
    async with database.sessions() as session:
        deck = await create_node(
            session, user.id, NodeCreate(type=NodeType.DECK, name="Finance", sense_ids=ids), config
        )
    await append(
        database.sessions,
        [
            Artifact(
                id=0,
                sense_id=sense_id,
                theme_id=None,
                artifact_type=QuestionArtifactType.WORD_DEFINITION,
                payload={
                    "corrects": ["a financial institution"],
                    "distractors": [
                        {"word": "shop", "definition": "a retail business"},
                        {"word": "school", "definition": "a place for teaching"},
                        {"word": "park", "definition": "a public garden"},
                    ],
                },
            )
            for sense_id in ids
        ],
    )
    return user, deck, ids, config


@pytest.mark.parametrize(
    "selection, expected_indices, reasons",
    [
        (
            Selection.AUTO,
            [2, 1, 0, 3],
            [LearningState.DUE, LearningState.DUE, LearningState.NEW, LearningState.NOT_YET_DUE],
        ),
        (Selection.NEW, [0], [LearningState.NEW]),
        (Selection.DUE, [2, 1], [LearningState.DUE, LearningState.DUE]),
    ],
)
async def test_preparation_selects_ordered_scope_and_never_changes_learning_state(
    database, prepared_library, selection, expected_indices, reasons
):
    user, deck, ids, config = prepared_library
    async with database.sessions() as session:
        preferences = await preparation.normalize_preparation(
            session, user.id, config, selection=selection
        )
        result = await preparation.prepare(
            session,
            database.sessions,
            UnusedProvider(),
            InMemoryStore(max_entries=1024, ttl=30),
            user.id,
            deck["id"],
            config,
            selection=selection,
            preferences=preferences,
        )
    assert [bundle["sense"].id for bundle in result["bundles"]] == [
        ids[index] for index in expected_indices
    ]
    assert [bundle["reason"] for bundle in result["bundles"]] == reasons
    assert result["actual_question_count"] == len(expected_indices)
    assert result["preferences"].formats == [ResponseFormat.SINGLE_CHOICE]
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(UserSense)) == 3
        assert await session.scalar(select(func.sum(UserSense.review_count))) == 3
        assert await session.scalar(select(func.count()).select_from(ReviewReceipt)) == 0


async def test_preparation_uses_fresh_plan_preserves_saved_preferences_and_applies_limit(
    database, prepared_library
):
    user, deck, ids, config = prepared_library
    async with database.sessions() as session, session.begin():
        (await session.get(User, user.id)).plan = Plan.PRO
    assert user.plan is Plan.FREE
    async with database.sessions() as session:
        preferences = await preparation.normalize_preparation(
            session, user.id, config, max_sense_count=1
        )
        result = await preparation.prepare(
            session,
            database.sessions,
            UnusedProvider(),
            None,
            user.id,
            deck["id"],
            config,
            preferences=preferences,
        )
    assert result["actual_sense_count"] == 1
    assert result["bundles"][0]["sense"].id == ids[2]
    assert result["preferences"].formats == [ResponseFormat.SHORT_ANSWER]
    async with database.sessions() as session:
        assert (await session.get(User, user.id)).settings["learning"]["formats"] == [
            ResponseFormat.SHORT_ANSWER
        ]


async def test_preparation_cannot_read_foreign_private_scope(database, prepared_library):
    _, deck, _, config = prepared_library
    foreign, _ = await account(database.sessions)
    async with database.sessions() as session:
        with pytest.raises(Problem) as error:
            await preparation.prepare(
                session,
                database.sessions,
                UnusedProvider(),
                None,
                foreign.id,
                deck["id"],
                config,
                preferences=await preparation.normalize_preparation(session, foreign.id, config),
            )
        assert error.value.status == 404
