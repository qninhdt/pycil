import asyncio

import pytest
from sqlalchemy import select, text

from pycil.vocabulary.content import delete_word, edit_word
from pycil.vocabulary.models import Word
from pycil.vocabulary.revisions import (
    ContentRevision,
    baseline,
    capture,
    head,
    publish,
    replay,
    serialize,
)
from tests.support.vocabulary import neutral_word


async def test_create_edit_noop_rollback_and_delete_reconstruct_history(database):
    identifier, _ = await neutral_word(database.sessions)
    async with database.sessions() as session:
        original = await replay(session, identifier)
        assert original == await serialize(session, identifier)
        first = await head(session)
    revision = await edit_word(database.sessions, identifier, lemma="lender", aliases=["bank"])
    assert revision > first
    assert await edit_word(database.sessions, identifier, lemma="lender", aliases=["bank"]) is None
    async with database.sessions() as session:
        current = await replay(session, identifier)
        assert current["lemma"] == "lender"
        assert current == await serialize(session, identifier)
        assert await replay(session, identifier, through=first) == original
    async with database.sessions() as session:
        with pytest.raises(RuntimeError, match="abort"):
            async with session.begin():
                before = await capture(session, [identifier])
                (await session.get(Word, identifier)).lemma = "rolled back"
                await publish(session, before)
                raise RuntimeError("abort")
    async with database.sessions() as session:
        assert await head(session) == revision
    tombstone = await delete_word(database.sessions, identifier)
    async with database.sessions() as session:
        assert await replay(session, identifier) is None
        patch = await session.scalar(
            select(ContentRevision.op).where(ContentRevision.id == tombstone)
        )
        assert patch == [{"op": "replace", "path": "", "value": None}]
        assert await replay(session, identifier, through=revision) == current


async def test_publication_ids_cannot_skip_a_delayed_committer(database):
    first, _ = await neutral_word(database.sessions)
    second = await edit_word(database.sessions, first, lemma="lender")
    locked, allow_commit, second_started = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def slow():
        async with database.sessions() as session, session.begin():
            before = await capture(session, [first])
            (await session.get(Word, first)).lemma = "first change"
            revision = await publish(session, before)
            locked.set()
            await allow_commit.wait()
        return revision

    async def later():
        await locked.wait()
        async with database.sessions() as session, session.begin():
            # Independent entity: publication ordering, not the word lock, must block this.
            word = Word(lemma="independent", match_key="independent")
            session.add(word)
            await session.flush()
            second_started.set()
            revision = await publish(session, {word.id: None})
        return revision

    a, b = asyncio.create_task(slow()), asyncio.create_task(later())
    try:
        await second_started.wait()
        async with database.sessions() as session:
            assert await head(session) == second
        await asyncio.sleep(0.05)
        assert not b.done()
        allow_commit.set()
        one, two = await asyncio.gather(a, b)
        assert second < one < two
    finally:
        allow_commit.set()
        await asyncio.gather(a, b, return_exceptions=True)


async def test_explicit_baseline_is_bounded_idempotent_and_required_before_legacy_edit(database):
    async with database.sessions() as session, session.begin():
        word = Word(lemma="legacy", match_key="legacy")
        session.add(word)
        await session.flush()
        identifier = word.id
    with pytest.raises(RuntimeError, match="baseline missing"):
        await edit_word(database.sessions, identifier, lemma="changed")
    assert await baseline(database.sessions, batch_size=1) == 1
    assert await baseline(database.sessions, batch_size=1) == 0
    await edit_word(database.sessions, identifier, lemma="changed")
    async with database.sessions() as session:
        assert (await replay(session, identifier))["lemma"] == "changed"
        assert (
            await session.scalar(
                text(
                    "SELECT cache_size FROM pg_sequences "
                    "WHERE sequencename='content_revision_id_seq'"
                )
            )
            == 1
        )


async def test_artifact_mutations_do_not_create_vocabulary_revisions(database):
    from pycil.study.artifacts.storage import append, remove
    from pycil.study.models import QuestionArtifact
    from tests.integration.study.test_artifact_banks import context, singleton

    _, sense = await neutral_word(database.sessions)
    async with database.sessions() as session:
        before = await head(session)
    saved = await append(database.sessions, [context(sense, i) for i in range(3)])
    single = (await append(database.sessions, [singleton(sense, "a financial institution")]))[0]
    await append(database.sessions, [singleton(sense, "a place that holds money")])
    assert await remove(database.sessions, saved[0].id)
    async with database.sessions() as session:
        assert await head(session) == before
        assert await session.get(QuestionArtifact, saved[0].id) is None
        assert await session.get(QuestionArtifact, single.id) is not None
        assert set(await session.scalars(select(ContentRevision.entity_type))) == {"word"}
