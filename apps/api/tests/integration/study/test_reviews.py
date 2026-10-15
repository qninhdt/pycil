import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from pycil.app.config import load_config
from pycil.app.http import Problem
from pycil.infrastructure.cache import MemoryCache
from pycil.library.models import NodeType
from pycil.library.nodes import create_node
from pycil.library.schemas import NodeCreate
from pycil.study.artifacts.schemas import Artifact
from pycil.study.artifacts.storage import append
from pycil.study.enums import (
    LearningState,
    QuestionArtifactType,
    QuestionType,
    ResponseFormat,
    Selection,
)
from pycil.study.models import DailyActivity, ReviewReceipt, UserSense
from pycil.study.preparation import prepare
from pycil.study.reviews import review
from pycil.study.schemas import Preparation, Review, ReviewBatch
from pycil.vocabulary.enums import EntryType, GenerationState, PartOfSpeech, Tier
from pycil.vocabulary.models import Sense, Word
from tests.support.account import account
from tests.support.artifacts import payloads
from tests.support.clock import frozen_datetime
from tests.support.vocabulary import neutral_word


async def test_alternate_word_credit_and_cross_word_definition_rejection_are_atomic(database):
    config = load_config()
    user, _ = await account(database.sessions)
    _, target_id = await neutral_word(database.sessions)
    async with database.sessions() as session, session.begin():
        word = Word(
            lemma="lender",
            match_key="lender",
            entry_type=EntryType.WORD,
            generation_state=GenerationState.DONE,
        )
        session.add(word)
        await session.flush()
        alternate = Sense(word_id=word.id, pos=PartOfSpeech.NOUN, tier=Tier.CORE)
        session.add(alternate)
        await session.flush()
    artifacts = await append(
        database.sessions,
        [
            Artifact(
                id=0,
                sense_id=target_id,
                theme_id=None,
                artifact_type=QuestionArtifactType.WORD_DEFINITION,
                payload=payloads()[QuestionArtifactType.WORD_DEFINITION],
            )
        ],
    )
    answer = Review(
        question_artifact_id=artifacts[0].id,
        question_type=QuestionType.DEFINITION_TO_WORD,
        format=ResponseFormat.SINGLE_WORD,
        diagnostics=dict(task_fit=True, spelling_error=True, sense_id=alternate.id),
        answered_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    invalid = Review(
        question_artifact_id=artifacts[0].id,
        question_type=QuestionType.WORD_TO_DEFINITION,
        format=ResponseFormat.SHORT_ANSWER,
        diagnostics=dict(sense_id=alternate.id, accuracy="accurate", coverage="sufficient"),
        answered_at=answer.answered_at,
    )
    async with database.sessions() as session:
        with pytest.raises(Problem) as error:
            await review(session, user.id, ReviewBatch(results=[answer, invalid]), uuid4(), config)
        assert error.value.code == "invalid_definition_sense"
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(UserSense)) == 0
        assert await session.scalar(select(func.count()).select_from(ReviewReceipt)) == 0
        assert await session.scalar(select(func.count()).select_from(DailyActivity)) == 0
    async with database.sessions() as session:
        accepted = await review(session, user.id, ReviewBatch(results=[answer]), uuid4(), config)
    assert accepted["results"][0]["sense_id"] == alternate.id
    assert accepted["evidence"][0]["recall"] == 1.0
    assert accepted["evidence"][0]["performance"] == 0.8
    async with database.sessions() as session:
        assert await session.get(UserSense, (user.id, target_id)) is None
        assert (await session.get(UserSense, (user.id, alternate.id))).review_count == 1


async def test_repeated_artifacts_share_one_update_and_acceptance_timezone(database, monkeypatch):
    config = load_config()
    user, _ = await account(database.sessions, settings={"timezone": "Asia/Ho_Chi_Minh"})
    _, sense_id = await neutral_word(database.sessions)
    artifacts = await append(
        database.sessions,
        [
            Artifact(
                id=0,
                sense_id=sense_id,
                theme_id=None,
                artifact_type=QuestionArtifactType.WORD_DEFINITION,
                payload=payloads()[QuestionArtifactType.WORD_DEFINITION],
            )
        ],
    )
    now = datetime(2026, 10, 13, 18, tzinfo=UTC)
    monkeypatch.setattr("pycil.study.reviews.datetime", frozen_datetime(now))
    first = Review(
        question_artifact_id=artifacts[0].id,
        question_type=QuestionType.DEFINITION_TO_WORD,
        format=ResponseFormat.SINGLE_CHOICE,
        diagnostics={"correct": True},
        answered_at=now - timedelta(hours=4),
    )
    second = Review.model_validate(
        first.model_dump()
        | {
            "answered_at": now - timedelta(hours=3),
            "diagnostics": {"correct": False},
        }
    )
    async with database.sessions() as session:
        result = await review(
            session, user.id, ReviewBatch(results=[first, second]), uuid4(), config
        )
    assert result["activity_day"] == "2026-10-14"
    assert len(result["results"]) == 1 and len(result["evidence"]) == 2
    async with database.sessions() as session:
        memory = await session.get(UserSense, (user.id, sense_id))
        assert memory.review_count == 1
        assert memory.last_exposure_at == second.answered_at
        activity = await session.scalar(select(DailyActivity))
        assert activity.day.isoformat() == result["activity_day"]
        assert activity.applied_events == 1 and activity.practice_events == 0


async def test_prepare_review_replay_is_atomic_and_changes_selection(database):
    config = load_config()
    _, sense_id = await neutral_word(database.sessions)
    user, _ = await account(
        database.sessions,
        settings={
            "learning": {
                "question_types": [QuestionType.DEFINITION_TO_WORD],
                "formats": [ResponseFormat.SINGLE_CHOICE],
                "max_sense_count": 1,
                "questions_per_sense": 1,
            }
        },
    )
    async with database.sessions() as session:
        deck = await create_node(
            session,
            user.id,
            NodeCreate(type=NodeType.DECK, name="Finance", sense_ids=[sense_id]),
            config,
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
                        {"word": "shop", "definition": "a place to buy goods"},
                        {"word": "school", "definition": "a place to learn"},
                        {"word": "park", "definition": "a public garden"},
                    ],
                },
            )
        ],
    )
    cache = MemoryCache(max_entries=1024, ttl=30)

    async def prepared(selection):
        async with database.sessions() as session:
            return Preparation.model_validate(
                await prepare(
                    session,
                    database.sessions,
                    None,
                    cache,
                    user.id,
                    deck["id"],
                    config,
                    selection=selection,
                )
            )

    fresh = await prepared(Selection.NEW)
    assert fresh.actual_sense_count == fresh.actual_question_count == 1
    assert fresh.bundles[0].reason == LearningState.NEW
    question = fresh.bundles[0].questions[0]
    assert question.question.correct.content == "bank"
    assert len(question.options) == 4
    batch = ReviewBatch(
        results=[
            Review(
                question_artifact_id=question.question.question_artifact_id,
                question_type=question.question.question_type,
                format=question.format,
                diagnostics={"correct": True},
                answered_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        ]
    )
    event_key = uuid4()

    async def submit(data):
        async with database.sessions() as session:
            return await review(session, user.id, data, event_key, config)

    first, replay = await asyncio.gather(submit(batch), submit(batch))
    assert first == replay
    assert first["results"][0]["sense_id"] == sense_id
    assert first["results"][0]["applied"] is True
    conflict = ReviewBatch(
        results=[
            Review.model_validate(
                batch.results[0].model_dump() | {"diagnostics": {"correct": False}}
            )
        ]
    )
    with pytest.raises(Problem) as error:
        await submit(conflict)
    assert error.value.status == 409
    async with database.sessions() as session:
        memory = await session.get(UserSense, (user.id, sense_id))
        assert memory.review_count == 1
        assert memory.due_at > datetime.now(UTC)
        assert await session.scalar(select(func.count()).select_from(ReviewReceipt)) == 1
        activity = await session.scalar(select(DailyActivity))
        assert activity.applied_events == 1
    assert (await prepared(Selection.NEW)).actual_sense_count == 0
    assert (await prepared(Selection.DUE)).actual_sense_count == 0
    early = await prepared(Selection.AUTO)
    assert early.actual_sense_count == 1
    assert early.bundles[0].reason == LearningState.NOT_YET_DUE


async def test_review_rejects_invalid_batch_and_old_evidence_cannot_overwrite_memory(
    database,
):
    config = load_config()
    user, _ = await account(database.sessions)
    _, sense_id = await neutral_word(database.sessions)
    artifacts = await append(
        database.sessions,
        [
            Artifact(
                id=0,
                sense_id=sense_id,
                theme_id=None,
                artifact_type=QuestionArtifactType.WORD_DEFINITION,
                payload={
                    "corrects": ["a financial institution"],
                    "distractors": [{"word": "shop", "definition": "a retailer"}],
                },
            )
        ],
    )
    now = datetime.now(UTC)
    item = Review(
        question_artifact_id=artifacts[0].id,
        question_type=QuestionType.DEFINITION_TO_WORD,
        format=ResponseFormat.SINGLE_CHOICE,
        diagnostics={"correct": True},
        answered_at=now - timedelta(seconds=1),
    )

    async def submit(items):
        async with database.sessions() as session:
            return await review(session, user.id, ReviewBatch(results=items), uuid4(), config)

    for invalid, code in [
        (item.model_copy(update={"answered_at": now + timedelta(days=1)}), "invalid_answered_at"),
        (item.model_copy(update={"question_artifact_id": 99999}), "question_artifact_not_found"),
    ]:
        with pytest.raises(Problem) as error:
            await submit([item, invalid])
        assert error.value.code == code
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(UserSense)) == 0
        assert await session.scalar(select(func.count()).select_from(ReviewReceipt)) == 0
        assert await session.scalar(select(func.count()).select_from(DailyActivity)) == 0
    first = await submit([item])
    older = Review.model_validate(
        item.model_dump()
        | {"answered_at": now - timedelta(days=1), "diagnostics": {"correct": False}}
    )
    late = await submit([older])
    assert late["results"][0]["applied"] is False
    assert late["results"][0]["elo"] == first["results"][0]["elo"]
    async with database.sessions() as session:
        memory = await session.get(UserSense, (user.id, sense_id))
        assert memory.last_exposure_at == item.answered_at
        assert memory.review_count == 1 and memory.lapse_count == 0
        activity = await session.scalar(select(DailyActivity))
        assert activity.applied_events == 1 and activity.practice_events == 1


async def test_distinct_concurrent_review_batches_do_not_lose_memory_or_activity_updates(database):
    config = load_config()
    user, _ = await account(database.sessions)
    _, sense_id = await neutral_word(database.sessions)
    artifacts = await append(
        database.sessions,
        [
            Artifact(
                id=0,
                sense_id=sense_id,
                theme_id=None,
                artifact_type=QuestionArtifactType.WORD_DEFINITION,
                payload={
                    "corrects": ["a financial institution"],
                    "distractors": [{"word": "shop", "definition": "a retailer"}],
                },
            )
        ],
    )
    now = datetime.now(UTC) - timedelta(seconds=1)
    batch = ReviewBatch(
        results=[
            Review(
                question_artifact_id=artifacts[0].id,
                question_type=QuestionType.DEFINITION_TO_WORD,
                format=ResponseFormat.SINGLE_CHOICE,
                diagnostics={"correct": True},
                answered_at=now,
            )
        ]
    )
    gate = asyncio.Barrier(2)

    async def submit():
        async with database.sessions() as session:
            await gate.wait()
            return await review(session, user.id, batch, uuid4(), config)

    results = await asyncio.gather(submit(), submit())
    assert all(result["results"][0]["applied"] for result in results)
    async with database.sessions() as session:
        memory = await session.get(UserSense, (user.id, sense_id))
        assert memory.review_count == 2
        assert await session.scalar(select(func.count()).select_from(ReviewReceipt)) == 2
        activity = await session.scalar(select(DailyActivity))
        assert activity.applied_events == 2
