import asyncio

import pytest
from sqlalchemy import select, text

from pycil.infrastructure.content_revisions import (
    ContentRevision,
    baseline,
    capture,
    head,
    publish,
    replay,
    serialize,
)
from pycil.vocabulary.content import delete_word, edit_word
from pycil.vocabulary.models import Word
from tests.support.vocabulary import neutral_word


async def test_create_edit_noop_rollback_and_delete_reconstruct_history(database):
    identifier, _ = await neutral_word(database.sessions)
    async with database.sessions() as session:
        original = await replay(session, "word", identifier)
        assert original == await serialize(session, "word", identifier)
        first = await head(session)
    revision = await edit_word(database.sessions, identifier, lemma="lender", aliases=["bank"])
    assert revision > first
    assert await edit_word(database.sessions, identifier, lemma="lender", aliases=["bank"]) is None
    async with database.sessions() as session:
        current = await replay(session, "word", identifier)
        assert current["lemma"] == "lender"
        assert current == await serialize(session, "word", identifier)
        assert await replay(session, "word", identifier, through=first) == original
    async with database.sessions() as session:
        with pytest.raises(RuntimeError, match="abort"):
            async with session.begin():
                before = await capture(session, [("word", identifier)])
                (await session.get(Word, identifier)).lemma = "rolled back"
                await publish(session, before)
                raise RuntimeError("abort")
    async with database.sessions() as session:
        assert await head(session) == revision
    tombstone = await delete_word(database.sessions, identifier)
    async with database.sessions() as session:
        assert await replay(session, "word", identifier) is None
        patch = await session.scalar(
            select(ContentRevision.op).where(ContentRevision.id == tombstone)
        )
        assert patch == [{"op": "replace", "path": "", "value": None}]
        assert await replay(session, "word", identifier, through=revision) == current


async def test_publication_ids_cannot_skip_a_delayed_committer(database):
    first, _ = await neutral_word(database.sessions)
    second = await edit_word(database.sessions, first, lemma="lender")
    locked, allow_commit, second_started = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def slow():
        async with database.sessions() as session, session.begin():
            before = await capture(session, [("word", first)])
            (await session.get(Word, first)).lemma = "first change"
            revision = await publish(session, before)
            locked.set()
            await allow_commit.wait()
        return revision

    async def later():
        await locked.wait()
        async with database.sessions() as session, session.begin():
            # Independent entity: publication ordering, not the word lock, must block this.
            from pycil.themes.models import Theme

            theme = Theme(key="test", name="Test", voice="Plain", diction="Simple")
            session.add(theme)
            await session.flush()
            second_started.set()
            revision = await publish(session, {("theme", theme.id): None})
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
        assert (await replay(session, "word", identifier))["lemma"] == "changed"
        assert (
            await session.scalar(
                text(
                    "SELECT cache_size FROM pg_sequences "
                    "WHERE sequencename='content_revision_id_seq'"
                )
            )
            == 1
        )


async def test_artifact_merge_removal_and_dense_position_changes_replay(database):
    from pycil.study.artifacts.storage import append, remove
    from tests.integration.study.test_artifact_banks import context, singleton

    _, sense = await neutral_word(database.sessions)
    saved = await append(database.sessions, [context(sense, i) for i in range(3)])
    single = (await append(database.sessions, [singleton(sense, "a financial institution")]))[0]
    await append(database.sessions, [singleton(sense, "a place that holds money")])
    async with database.sessions() as session:
        value = await replay(session, "question_artifact", single.id)
        assert value == await serialize(session, "question_artifact", single.id)
        assert len(value["payload"]["corrects"]) == 2
        before = await head(session)
    await remove(database.sessions, saved[0].id)
    async with database.sessions() as session:
        assert await replay(session, "question_artifact", saved[0].id) is None
        for artifact in [*saved[1:], single]:
            assert await replay(session, "question_artifact", artifact.id) == await serialize(
                session, "question_artifact", artifact.id
            )
        assert (await replay(session, "question_artifact", single.id, through=before))[
            "position"
        ] == 4


async def test_theme_cascade_and_word_cascade_keep_complete_history(database):
    from pycil.study.artifacts.storage import append
    from pycil.themes.service import create_theme, delete_theme
    from pycil.vocabulary.generation.themed import ensure_word_theme
    from tests.integration.study.test_artifact_banks import context
    from tests.integration.themes.test_namespaces import ThemeProvider

    word, sense = await neutral_word(database.sessions)
    provider = ThemeProvider()
    theme = await create_theme(database.sessions, provider, "space", "Space", "life in space")
    await ensure_word_theme(database.sessions, provider, word, theme.key, 1)
    artifact = context(sense, 0).model_copy(update={"theme_id": theme.id})
    saved = (await append(database.sessions, [artifact]))[0]
    async with database.sessions() as session:
        assert await replay(session, "word", word) == await serialize(session, "word", word)
        themed_revision = await head(session)
    await delete_theme(database.sessions, theme.key)
    async with database.sessions() as session:
        assert await replay(session, "theme", theme.id) is None
        assert await replay(session, "question_artifact", saved.id) is None
        value = await replay(session, "word", word)
        assert value == await serialize(session, "word", word)
        assert len(value["definitions"]) == 1
        assert (
            len((await replay(session, "word", word, through=themed_revision))["definitions"]) == 2
        )
    neutral = (await append(database.sessions, [context(sense, 1)]))[0]
    await delete_word(database.sessions, word)
    async with database.sessions() as session:
        assert await replay(session, "word", word) is None
        assert await replay(session, "question_artifact", neutral.id) is None
