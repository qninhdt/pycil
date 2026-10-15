import asyncio

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select

from pycil.study.artifacts.schemas import Artifact
from pycil.study.artifacts.storage import append, bank_sizes, retrieve_many
from pycil.study.enums import QuestionArtifactType
from pycil.study.models import QuestionArtifact
from pycil.vocabulary.enums import EntryType, GenerationState, PartOfSpeech, Tier
from pycil.vocabulary.models import Sense, Word


@pytest.fixture
async def sense_id(database):
    async with database.sessions() as session, session.begin():
        word = Word(
            lemma="bank",
            match_key="bank",
            entry_type=EntryType.WORD,
            generation_state=GenerationState.DONE,
        )
        session.add(word)
        await session.flush()
        sense = Sense(word_id=word.id, pos=PartOfSpeech.NOUN, tier=Tier.CORE)
        session.add(sense)
        await session.flush()
        return sense.id


def context(sense_id, number):
    return Artifact(
        id=0,
        sense_id=sense_id,
        theme_id=None,
        artifact_type=QuestionArtifactType.CONTEXT_TO_WORD,
        payload={
            "context": f"A customer deposits money, situation {number}.",
            "distractors": ["shop", "school", "park"],
        },
    )


def singleton(sense_id, correct):
    return Artifact(
        id=0,
        sense_id=sense_id,
        theme_id=None,
        artifact_type=QuestionArtifactType.WORD_DEFINITION,
        payload={
            "corrects": [correct],
            "distractors": [{"word": "shop", "definition": "a place to buy goods"}],
        },
    )


async def test_context_bank_deduplicates_and_remains_sampleable_after_deletion(database, sense_id):
    artifacts = [context(sense_id, number) for number in range(5)]
    saved = await append(database.sessions, [*artifacts, artifacts[0]])
    assert len(saved) == 5
    assert await append(database.sessions, artifacts) == []
    async with database.sessions() as session, session.begin():
        await session.execute(delete(QuestionArtifact).where(QuestionArtifact.id == saved[1].id))
    request = (sense_id, QuestionArtifactType.CONTEXT_TO_WORD)
    assert (await bank_sizes(database.sessions, [request]))[request] == 4
    retrieved = await retrieve_many(database.sessions, [(*request, 4)])
    assert {item.id for item in retrieved} == {item.id for item in saved} - {saved[1].id}
    async with database.sessions() as session:
        positions = (
            await session.execute(select(QuestionArtifact.position, QuestionArtifact.type_position))
        ).all()
    assert sorted(positions) == [(i, i) for i in range(1, 5)]


async def test_concurrent_singleton_increments_merge_without_losing_answers(database, sense_id):
    barrier = asyncio.Barrier(2)

    async def increment(correct):
        await barrier.wait()
        return await append(database.sessions, [singleton(sense_id, correct)])

    await asyncio.gather(
        increment("a financial institution"),
        increment("an institution that holds money"),
    )
    retrieved = await retrieve_many(
        database.sessions, [(sense_id, QuestionArtifactType.WORD_DEFINITION, 1)]
    )
    assert len(retrieved) == 1
    assert set(retrieved[0].payload["corrects"]) == {
        "a financial institution",
        "an institution that holds money",
    }
    assert retrieved[0].payload["distractors"] == [
        {"word": "shop", "definition": "a place to buy goods"}
    ]


async def test_invalid_payload_never_partially_publishes_a_batch(database, sense_id):
    invalid = context(sense_id, 2).model_copy(update={"payload": {"context": "missing options"}})
    with pytest.raises(ValidationError):
        await append(database.sessions, [context(sense_id, 1), invalid])
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(QuestionArtifact)) == 0


async def test_missing_sense_rolls_back_whole_batch_and_preserves_existing_cache(
    database, sense_id
):
    from pycil.infrastructure.cache import MemoryCache
    from pycil.study.artifacts.storage import get_many
    from pycil.vocabulary.errors import InvalidResourceError

    cache = MemoryCache(max_entries=1024, ttl=30)
    original = await append(database.sessions, [singleton(sense_id, "a financial institution")])
    cached = await get_many(database.sessions, [original[0].id], cache=cache)
    with pytest.raises(InvalidResourceError):
        await append(
            database.sessions,
            [singleton(sense_id, "an institution holding deposits"), context(999999, 1)],
            cache=cache,
        )
    assert await get_many(database.sessions, [original[0].id], cache=cache) == cached
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(QuestionArtifact)) == 1
        row = await session.get(QuestionArtifact, original[0].id)
        assert "holding deposits" not in row.payload


async def test_successful_singleton_merge_invalidates_cached_payload(database, sense_id):
    from pycil.infrastructure.cache import MemoryCache
    from pycil.study.artifacts.storage import get_many

    cache = MemoryCache(max_entries=1024, ttl=30)
    saved = await append(database.sessions, [singleton(sense_id, "a financial institution")])
    before = (await get_many(database.sessions, [saved[0].id], cache=cache))[0]
    changed = await append(
        database.sessions, [singleton(sense_id, "an institution holding deposits")], cache=cache
    )
    assert changed[0].id == before.id
    after = (await get_many(database.sessions, [before.id], cache=cache))[0]
    assert after.payload["corrects"] == [
        "a financial institution",
        "an institution holding deposits",
    ]
    assert before.payload["corrects"] == ["a financial institution"]
