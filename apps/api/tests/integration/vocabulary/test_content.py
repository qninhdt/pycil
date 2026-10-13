from datetime import UTC, datetime, timedelta

import pytest

from pycil.app.config import load_config
from pycil.app.http import Problem
from pycil.app.projections import viewer_context, word_previews
from pycil.library.models import NodeType
from pycil.library.nodes import create_node
from pycil.library.schemas import NodeCreate
from pycil.study.models import UserSense
from pycil.vocabulary.cache import ContentCache
from pycil.vocabulary.enums import PartOfSpeech, Tier
from pycil.vocabulary.models import Definition, Example, Sense
from pycil.vocabulary.words import get_sense_previews, get_senses, get_word
from tests.support.account import account
from tests.support.vocabulary import neutral_word


async def test_detached_batched_content_reads_skip_missing_ids_and_return_complete_neutral_group(
    database,
):
    word_id, sense_id = await neutral_word(database.sessions)
    cache = ContentCache()
    word = await get_word(database.sessions, word_id, cache=cache)
    assert word.id == word_id and word.senses[0].id == sense_id
    assert word.senses[0].definition.content == "a financial institution"
    assert word.senses[0].examples[0].content == "The [bank] opens at nine."
    assert await get_word(database.sessions, 99999, cache=cache) is None
    senses = await get_senses(database.sessions, [sense_id, 99999])
    assert [entry.id for entry in senses] == [sense_id]
    previews = await get_sense_previews(database.sessions, [sense_id, 99999])
    assert [entry["sense_id"] for entry in previews] == [sense_id]
    assert all("learning" not in entry and "user_id" not in entry for entry in previews)


async def test_word_preview_hydration_keeps_complete_groups_and_rejects_overflow(database):
    word_id, first_id = await neutral_word(database.sessions)
    config = load_config()
    config = config.model_copy(
        update={
            "projections": config.projections.model_copy(
                update={"max_word_senses": 2, "inline_examples": 1}
            )
        }
    )
    async with database.sessions() as session, session.begin():
        second = Sense(word_id=word_id, pos=PartOfSpeech.NOUN, tier=Tier.CORE)
        session.add(second)
        await session.flush()
        session.add_all(
            [
                Definition(sense_id=second.id, theme_id=None, content="the land beside a river"),
                Example(sense_id=second.id, theme_id=None, content="We sat on the [bank]."),
                Example(sense_id=second.id, theme_id=None, content="The [bank] was muddy."),
            ]
        )
    async with database.sessions() as session:
        result = await word_previews(session, database.sessions, [word_id], config)
    assert [sense.id for sense in result[0]["senses"]] == [first_id, second.id]
    assert len(result[0]["senses"][1].examples) == 1
    assert result[0]["senses"][1].definition.content == "the land beside a river"
    for identifiers, limit, code in [
        ([word_id], 1, "lexical_batch_too_large"),
        ([word_id, 99999], 2, "word_not_found"),
    ]:
        limited = config.model_copy(
            update={"projections": config.projections.model_copy(update={"max_word_senses": limit})}
        )
        async with database.sessions() as session:
            with pytest.raises(Problem) as error:
                await word_previews(session, database.sessions, identifiers, limited)
            assert error.value.code == code


async def test_viewer_context_never_reuses_another_users_memory_or_private_sources(database):
    _, sense_id = await neutral_word(database.sessions)
    owner, _ = await account(database.sessions)
    other, _ = await account(database.sessions)
    config = load_config()
    async with database.sessions() as session:
        deck = await create_node(
            session,
            owner.id,
            NodeCreate(type=NodeType.DECK, name="Private finance", sense_ids=[sense_id]),
            config,
        )
    now = datetime.now(UTC)
    async with database.sessions() as session, session.begin():
        session.add(
            UserSense(
                user_id=owner.id,
                sense_id=sense_id,
                stability=1,
                difficulty=5,
                elo=1100,
                last_exposure_at=now - timedelta(days=1),
                due_at=now,
                review_count=1,
                lapse_count=0,
            )
        )
    async with database.sessions() as session:
        personal = await viewer_context(session, owner.id, config, [sense_id])
    async with database.sessions() as session:
        unrelated = await viewer_context(session, other.id, config, [sense_id])
    assert personal["studied"] == personal["due"] == 1
    assert personal["senses"][0]["decks"][0]["id"] == deck["id"]
    assert unrelated["new"] == 1 and unrelated["studied"] == unrelated["due"] == 0
    assert unrelated["senses"][0]["decks"] == [] and unrelated["senses"][0]["deck_count"] == 0
    async with database.sessions() as session:
        with pytest.raises(Problem) as error:
            await viewer_context(session, owner.id, config, [sense_id, sense_id])
        assert error.value.code == "context_too_large"
