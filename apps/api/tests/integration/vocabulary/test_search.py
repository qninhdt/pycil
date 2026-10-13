import asyncio

import pytest
from sqlalchemy import select

from pycil.vocabulary.enums import (
    EntryType,
    GenerationState,
    HitKind,
    Inflection,
    MatchKind,
    PartOfSpeech,
    Tier,
)
from pycil.vocabulary.models import Sense, SenseForm, SensePattern, Word, WordAlias, WordReference
from pycil.vocabulary.references.importer import import_reference
from pycil.vocabulary.search import SearchIndex
from tests.support.reference import reference_file, reference_word


async def test_search_ranking_alias_forms_deduplication_and_reference_selection(database, tmp_path):
    records = [reference_word(1, 101), reference_word(2, 102)]
    records[1] = records[1] | {"lemma": "banker", "display_form": "banker"}
    await import_reference(database.sessions, reference_file(tmp_path / "reference.jsonl", records))
    async with database.sessions() as session, session.begin():
        words = [
            Word(
                lemma=value,
                match_key=value,
                entry_type=EntryType.WORD,
                generation_state=GenerationState.DONE,
            )
            for value in ["bank", "banking", "riverbank"]
        ]
        session.add_all(words)
        await session.flush()
        sense = Sense(word_id=words[0].id, pos=PartOfSpeech.NOUN, tier=Tier.CORE)
        session.add(sense)
        await session.flush()
        session.add_all(
            [
                WordAlias(word_id=words[0].id, content="lender", match_key="lender"),
                SenseForm(
                    sense_id=sense.id,
                    surface="banks",
                    match_key="banks",
                    head_key="banks",
                    inf=Inflection.PLURAL,
                ),
            ]
        )
    index = SearchIndex(database.sessions)
    await index.start()
    try:
        results = (await index.search("bank", True, limit=10)).items
        assert [hit.match_kind for hit in results[:2]] == [MatchKind.EXACT, MatchKind.EXACT]
        assert results[0].kind is HitKind.WORD and results[1].kind is HitKind.REFERENCE
        assert any(hit.match_kind is MatchKind.PREFIX for hit in results)
        assert any(hit.match_kind is MatchKind.SUBSTRING for hit in results)
        assert len(
            {
                (hit.kind, getattr(hit, "word_id", getattr(hit, "reference_id", None)))
                for hit in results
            }
        ) == len(results)
        assert (await index.search("lender")).items[0].word_id == words[0].id
        assert (await index.search("banks")).items[0].word_id == words[0].id
        assert all(hit.kind is HitKind.WORD for hit in (await index.search("bank")).items)
        assert len((await index.search("bank", True, limit=1)).items) == 1
        assert (await index.search("banx")).items[0].match_kind is MatchKind.FUZZY
    finally:
        await index.close()


async def test_index_update_replaces_stale_documents_consumes_reference_and_preserves_other_word(
    database, tmp_path
):
    await import_reference(
        database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
    )
    async with database.sessions() as session, session.begin():
        word = Word(
            lemma="give {sb} a hand",
            match_key="give {sb} a hand",
            entry_type=EntryType.EXPRESSION,
            generation_state=GenerationState.DONE,
        )
        other = Word(
            lemma="untouched",
            match_key="untouched",
            entry_type=EntryType.WORD,
            generation_state=GenerationState.DONE,
        )
        session.add_all([word, other])
        await session.flush()
        sense = Sense(word_id=word.id, pos=PartOfSpeech.VERB, tier=Tier.CORE)
        session.add(sense)
        await session.flush()
        session.add_all(
            [
                SensePattern(sense_id=sense.id, content="give {sb} a hand", head_key="give"),
                SenseForm(
                    sense_id=sense.id,
                    surface="gave",
                    match_key="gave",
                    head_key="gave",
                    inf=Inflection.PAST,
                ),
            ]
        )
    index = SearchIndex(database.sessions)
    await index.start()
    try:
        assert (await index.search("gave Jo a hand")).items[0].word_id == word.id
        async with database.sessions() as session, session.begin():
            stored = await session.get(Word, word.id)
            stored.lemma = stored.match_key = "assist"
            session.add(WordReference(word_id=word.id, source_id=1))
            pattern = await session.scalar(
                select(SensePattern).where(SensePattern.sense_id == sense.id)
            )
            await session.delete(pattern)
        await asyncio.gather(index.update(word.id), index.update(other.id))
        assert not (await index.search("give Jo a hand")).items
        assert (await index.search("assist")).items[0].word_id == word.id
        assert (await index.search("untouched")).items[0].word_id == other.id
        assert not any(
            hit.kind is HitKind.REFERENCE for hit in (await index.search("bank", True)).items
        )
    finally:
        await index.close()


async def test_cancelled_index_update_joins_native_publication_and_keeps_visible_snapshot(
    database, monkeypatch
):
    import threading

    from tests.support.vocabulary import neutral_word

    word_id, _ = await neutral_word(database.sessions)
    index = SearchIndex(database.sessions)
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    task = None
    try:
        await index.start()
        async with database.sessions() as session, session.begin():
            word = await session.get(Word, word_id)
            word.lemma, word.match_key = "lender", "lender"
        documents = index.documents

        def blocked_documents(*args):
            started.set()
            try:
                if not release.wait(timeout=5):
                    raise TimeoutError("native publication was not released")
                yield from documents(*args)
            finally:
                finished.set()

        monkeypatch.setattr(index, "documents", blocked_documents)
        task = asyncio.create_task(index.update(word_id))
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and not finished.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
        assert [hit.word_id for hit in (await index.search("lender")).items] == [word_id]
        assert (await index.search("bank")).items == []
    finally:
        release.set()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        await index.close()
