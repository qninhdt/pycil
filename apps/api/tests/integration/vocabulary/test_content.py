from datetime import UTC, datetime, timedelta

import pytest
from cachetools import TTLCache
from sqlalchemy import event

from pycil.app.config import load_config
from pycil.app.http import Problem
from pycil.app.projections import viewer_context, word_previews
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.library.models import NodeType
from pycil.library.nodes import create_node
from pycil.library.schemas import NodeCreate
from pycil.study.models import UserSense
from pycil.vocabulary import content
from pycil.vocabulary.content import delete_word, edit_word
from pycil.vocabulary.enums import PartOfSpeech, Tier
from pycil.vocabulary.models import Definition, Example, Sense
from pycil.vocabulary.schemas import CachedWord
from pycil.vocabulary.words import get_sense_previews, get_senses, get_word
from tests.support.account import account
from tests.support.vocabulary import neutral_word


async def test_detached_batched_content_reads_skip_missing_ids_and_return_complete_neutral_group(
    database,
):
    word_id, sense_id = await neutral_word(database.sessions)
    store = InMemoryStore(max_entries=1024, ttl=30)
    word = await get_word(database.sessions, word_id, word_store=store)
    assert word.id == word_id and word.senses[0].id == sense_id
    assert word.senses[0].definition.content == "a financial institution"
    assert word.senses[0].examples[0].content == "The [bank] opens at nine."
    assert await get_word(database.sessions, 99999, word_store=store) is None
    senses = await get_senses(database.sessions, [sense_id, 99999])
    assert [entry.id for entry in senses] == [sense_id]
    previews = await get_sense_previews(database.sessions, [sense_id, 99999])
    assert [entry["sense_id"] for entry in previews] == [sense_id]
    assert all("learning" not in entry and "user_id" not in entry for entry in previews)


async def test_separate_content_caches_share_senses_and_serve_full_hits_without_sql(database):
    word_id, sense_id = await neutral_word(database.sessions)
    now = [0]
    words, senses = InMemoryStore(1, 30), InMemoryStore(4, 5)
    words.values = TTLCache(maxsize=1, ttl=30, timer=lambda: now[0])
    senses.values = TTLCache(maxsize=4, ttl=5, timer=lambda: now[0])
    original = await get_word(database.sessions, word_id, word_store=words, sense_store=senses)
    metadata = words.get(word_id)
    assert isinstance(metadata, CachedWord)
    assert not hasattr(metadata, "senses")
    assert metadata.sense_ids == (sense_id,)
    assert senses.get(sense_id) is original.senses[0]
    statements = []

    def record(*args):
        statements.append(args[2])

    event.listen(database.engine.sync_engine, "before_cursor_execute", record)
    try:
        direct = await get_senses(database.sessions, [sense_id, sense_id], store=senses)
        assert direct[0] is direct[1] is original.senses[0]
        hit = await get_word(database.sessions, word_id, word_store=words, sense_store=senses)
        assert hit is not original and hit.senses[0] is original.senses[0]
        hit.senses.clear()
        again = await get_word(database.sessions, word_id, word_store=words, sense_store=senses)
        assert again.senses[0] is original.senses[0]
        assert statements == []
        now[0] = 5
        assert senses.get(sense_id) is None
        rehydrated = await get_word(
            database.sessions, word_id, word_store=words, sense_store=senses
        )
        assert rehydrated.model_dump(mode="json") == original.model_dump(mode="json")
        assert rehydrated.senses[0] is senses.get(sense_id)
        assert len(statements) == 1
        assert words.get(word_id) is metadata
        words.clear()
        assert words.get(word_id) is None
        assert senses.get(sense_id) is rehydrated.senses[0]
    finally:
        event.remove(database.engine.sync_engine, "before_cursor_execute", record)


async def test_sense_partial_misses_are_deduplicated_batched_and_keep_requested_order(database):
    word_id, first_id = await neutral_word(database.sessions)
    async with database.sessions() as session, session.begin():
        second = Sense(word_id=word_id, pos=PartOfSpeech.NOUN, tier=Tier.CORE)
        session.add(second)
        await session.flush()
    store = InMemoryStore(4, 30)
    first = (await get_senses(database.sessions, [first_id], store=store))[0]
    identifiers = [second.id, first_id, second.id, *range(10000, 10500)]
    statements = []

    def record(*args):
        statements.append(args[2])

    event.listen(database.engine.sync_engine, "before_cursor_execute", record)
    try:
        found = await get_senses(database.sessions, identifiers, store=store)
    finally:
        event.remove(database.engine.sync_engine, "before_cursor_execute", record)
    assert [sense.id for sense in found] == [second.id, first_id, second.id]
    assert found[1] is first and found[0] is found[2] is store.get(second.id)
    assert len(statements) == 2


async def test_stale_word_metadata_recovers_once_after_external_deletion(database):
    word_id, sense_id = await neutral_word(database.sessions)
    words, senses = InMemoryStore(2, 30), InMemoryStore(4, 30)
    await get_word(database.sessions, word_id, word_store=words, sense_store=senses)
    await delete_word(database.sessions, word_id)
    senses.discard(sense_id)
    statements = []

    def record(*args):
        statements.append(args[2])

    event.listen(database.engine.sync_engine, "before_cursor_execute", record)
    try:
        assert (
            await get_word(database.sessions, word_id, word_store=words, sense_store=senses) is None
        )
    finally:
        event.remove(database.engine.sync_engine, "before_cursor_execute", record)
    assert words.get(word_id) is None and senses.get(sense_id) is None
    assert len(statements) == 2


async def test_committed_lexical_edits_clear_both_stores_but_rollback_does_not(
    database, monkeypatch
):
    word_id, sense_id = await neutral_word(database.sessions)
    words, senses = InMemoryStore(2, 30), InMemoryStore(4, 30)
    await get_word(database.sessions, word_id, word_store=words, sense_store=senses)
    publish = content.publish

    async def fail(*args):
        raise RuntimeError("publication failed")

    monkeypatch.setattr(content, "publish", fail)
    with pytest.raises(RuntimeError, match="publication failed"):
        await edit_word(
            database.sessions, word_id, lemma="lender", word_store=words, sense_store=senses
        )
    assert words.get(word_id).lemma == "bank" and senses.get(sense_id) is not None
    monkeypatch.setattr(content, "publish", publish)
    await edit_word(
        database.sessions, word_id, lemma="lender", word_store=words, sense_store=senses
    )
    assert words.get(word_id) is None and senses.get(sense_id) is None
    fresh = await get_word(database.sessions, word_id, word_store=words, sense_store=senses)
    assert fresh.lemma == "lender"


async def test_word_preview_hydration_keeps_complete_groups_and_rejects_overflow(database):
    word_id, first_id = await neutral_word(database.sessions)
    config = load_config()
    config = config.model_copy(
        update={
            "product": config.product.model_copy(
                update={
                    "projections": config.product.projections.model_copy(
                        update={"max_word_senses": 2, "inline_examples": 1}
                    )
                }
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
    senses = InMemoryStore(4, 30)
    await get_word(database.sessions, word_id, sense_store=senses)
    async with database.sessions() as session:
        result = await word_previews(
            session, database.sessions, [word_id], config, sense_store=senses
        )
    assert len(senses.get(second.id).examples) == 2
    assert result[0]["senses"][1].definition is senses.get(second.id).definition
    assert [sense.id for sense in result[0]["senses"]] == [first_id, second.id]
    assert len(result[0]["senses"][1].examples) == 1
    assert result[0]["senses"][1].definition.content == "the land beside a river"
    for identifiers, limit, code in [
        ([word_id], 1, "lexical_batch_too_large"),
        ([word_id, 99999], 2, "word_not_found"),
    ]:
        limited = config.model_copy(
            update={
                "product": config.product.model_copy(
                    update={
                        "projections": config.product.projections.model_copy(
                            update={"max_word_senses": limit}
                        )
                    }
                )
            }
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
