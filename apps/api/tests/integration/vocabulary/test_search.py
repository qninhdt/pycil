import asyncio

import pytest

from pycil.vocabulary.enums import (
    EntryType,
    GenerationState,
    HitKind,
    Inflection,
    MatchKind,
    PartOfSpeech,
    Tier,
)
from pycil.vocabulary.models import Sense, SenseForm, Word, WordAlias, WordReference
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


def fast_policy():
    from pycil.app.config import load_config

    return load_config().runtime.search.model_copy(
        update={
            "poll_interval_seconds": 0.02,
            "ownership_retry_seconds": 0.02,
            "retry_jitter_seconds": 0,
            "startup_timeout_seconds": 10,
            "publication_timeout_seconds": 3,
        }
    )


async def create_word(sessions, lemma):
    from pycil.infrastructure.content_revisions import publish

    async with sessions() as session, session.begin():
        word = Word(
            lemma=lemma,
            match_key=lemma,
            entry_type=EntryType.WORD,
            generation_state=GenerationState.DONE,
        )
        session.add(word)
        await session.flush()
        await publish(session, {("word", word.id): None})
        return word.id


async def test_owner_replaces_edits_deletions_and_restores_unlinked_reference(database, tmp_path):
    from sqlalchemy import delete

    from pycil.infrastructure.content_revisions import capture, publish
    from pycil.vocabulary.content import delete_word, edit_word

    await import_reference(
        database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
    )
    index = SearchIndex(database.sessions, str(tmp_path / "index"), policy=fast_policy())
    await index.start()
    try:
        word_id = await create_word(database.sessions, "bank")
        other_id = await create_word(database.sessions, "untouched")
        async with database.sessions() as session, session.begin():
            before = await capture(session, [("word", word_id)])
            session.add(WordReference(word_id=word_id, source_id=1))
            revision = await publish(session, before)
        await index.wait_for_revision(revision)
        assert all(hit.kind is HitKind.WORD for hit in (await index.search("bank", True)).items)
        await edit_word(
            database.sessions, word_id, lemma="lender", aliases=["financial institution"]
        )
        await index.update(word_id)
        assert not (await index.search("bank")).items
        assert (await index.search("financial institution")).items[0].word_id == word_id
        async with database.sessions() as session, session.begin():
            before = await capture(session, [("word", word_id)])
            await session.execute(delete(WordReference).where(WordReference.word_id == word_id))
            revision = await publish(session, before)
        await index.wait_for_revision(revision)
        assert (await index.search("bank", True)).items[0].kind is HitKind.REFERENCE
        revision = await delete_word(database.sessions, word_id)
        await index.wait_for_revision(revision)
        assert not (await index.search("lender")).items
        assert (await index.search("untouched")).items[0].word_id == other_id
    finally:
        await index.close()


async def test_shared_directory_has_one_owner_and_takeover_reuses_cursor(
    database, tmp_path, monkeypatch
):
    from pycil.vocabulary.content import edit_word

    directory = str(tmp_path / "shared")
    first, second = (
        SearchIndex(database.sessions, directory, policy=fast_policy()),
        SearchIndex(database.sessions, directory, policy=fast_policy()),
    )
    await asyncio.gather(first.start(), second.start())
    owner, standby = (first, second) if first.is_owner else (second, first)
    try:
        assert owner.is_owner and not standby.is_owner
        word = await create_word(database.sessions, "bank")
        await asyncio.gather(first.update(word), second.update(word))
        assert first.cursor() == second.cursor()

        async def unexpected_rebuild(*args):
            pytest.fail("compatible shared checkpoint must survive takeover")

        monkeypatch.setattr(standby, "rebuild", unexpected_rebuild)
        await owner.close()
        async with asyncio.timeout(3):
            while not standby.is_owner:
                await asyncio.sleep(0.02)
        await edit_word(database.sessions, word, lemma="lender")
        await standby.update(word)
        assert (await standby.search("lender")).items[0].word_id == word
    finally:
        await asyncio.gather(first.close(), second.close())


async def test_independent_indexes_apply_all_revisions_and_disconnected_reader_catches_up(
    database, tmp_path, monkeypatch
):
    from pycil.vocabulary.content import edit_word

    first = SearchIndex(database.sessions, str(tmp_path / "one"), policy=fast_policy())
    second = SearchIndex(database.sessions, str(tmp_path / "two"), policy=fast_policy())
    await asyncio.gather(first.start(), second.start())
    try:
        word = await create_word(database.sessions, "bank")
        await asyncio.gather(first.update(word), second.update(word))
        assert first.is_owner and second.is_owner
        await second.close()
        await edit_word(database.sessions, word, lemma="lender")
        await first.update(word)

        async def unexpected_rebuild(*args):
            pytest.fail("catch-up must be incremental")

        monkeypatch.setattr(second, "rebuild", unexpected_rebuild)
        await second.start()
        assert (await second.search("lender")).items[0].word_id == word
        assert first.cursor() == second.cursor()
    finally:
        await asyncio.gather(first.close(), second.close())


async def test_native_shutdown_joins_inflight_owner_and_rolls_back_uncommitted_batch(
    database, tmp_path, monkeypatch
):
    import threading

    from pycil.vocabulary.content import edit_word

    word = await create_word(database.sessions, "bank")
    index = SearchIndex(database.sessions, str(tmp_path / "index"), policy=fast_policy())
    await index.start()
    started, release = threading.Event(), threading.Event()
    documents = index.documents

    def blocked(*args):
        started.set()
        if not release.wait(5):
            raise TimeoutError("native publication not released")
        yield from documents(*args)

    monkeypatch.setattr(index, "documents", blocked)
    await edit_word(database.sessions, word, lemma="lender")
    closing = None
    try:
        assert await asyncio.to_thread(started.wait, 3)
        closing = asyncio.create_task(index.close())
        await asyncio.sleep(0.05)
        assert not closing.done()
        release.set()
        await closing
        monkeypatch.setattr(index, "documents", documents)
        await index.start()
        assert (await index.search("lender")).items[0].word_id == word
    finally:
        release.set()
        if closing:
            await closing
        await index.close()


async def test_bootstrap_snapshot_and_catchup_include_writes_during_build(
    database, tmp_path, monkeypatch
):
    first = await create_word(database.sessions, "first")
    index = SearchIndex(
        database.sessions,
        str(tmp_path / "index"),
        policy=fast_policy().model_copy(update={"rebuild_batch_size": 1}),
    )
    projection = index.projection
    inserted = None

    async def interleaved(*args, **options):
        nonlocal inserted
        if inserted is None:
            inserted = await create_word(database.sessions, "later")
        return await projection(*args, **options)

    monkeypatch.setattr(index, "projection", interleaved)
    try:
        await index.start()
        assert (await index.search("first")).items[0].word_id == first
        assert (await index.search("later")).items[0].word_id == inserted
    finally:
        await index.close()


async def test_failed_batch_keeps_checkpoint_and_restarts_without_rebuilding(
    database, tmp_path, monkeypatch
):
    from pycil.vocabulary.content import edit_word

    word = await create_word(database.sessions, "bank")
    index = SearchIndex(database.sessions, str(tmp_path / "index"), policy=fast_policy())
    await index.start()
    previous = index.cursor()
    documents = index.documents

    def failure(*args):
        yield from documents(*args)
        raise RuntimeError("native publication failed")

    monkeypatch.setattr(index, "documents", failure)
    try:
        await edit_word(database.sessions, word, lemma="lender")
        async with asyncio.timeout(3):
            while index.failure is None:
                await asyncio.sleep(0.02)
        assert index.cursor() == previous
        with pytest.raises(RuntimeError):
            index.ready()
        await index.close()
        monkeypatch.setattr(index, "documents", documents)
        await index.start()
        assert (await index.search("lender")).items[0].word_id == word
    finally:
        await index.close()


async def test_artifact_theme_only_revisions_advance_cursor_and_idle_index_stays_healthy(
    database, tmp_path
):
    from pycil.infrastructure.content_revisions import publish
    from pycil.themes.models import Theme

    index = SearchIndex(database.sessions, policy=fast_policy())
    await index.start()
    try:
        async with database.sessions() as session, session.begin():
            theme = Theme(key="plain", name="Plain", voice="Calm", diction="Simple")
            session.add(theme)
            await session.flush()
            revision = await publish(session, {("theme", theme.id): None})
        await index.wait_for_revision(revision)
        assert not (await index.search("plain")).items
        await index.health()
        index.last_success -= 1000
        # A successful empty owner poll restores health without an index commit.
        await asyncio.sleep(0.05)
        await index.health()
        assert index.cursor() == revision
    finally:
        await index.close()


async def test_four_process_readers_share_one_poller_and_recover_after_owner_sigkill(
    database, tmp_path
):
    import multiprocessing

    from pycil.infrastructure.content_revisions import head
    from pycil.vocabulary.content import delete_word, edit_word
    from tests.support.search_worker import run

    context = multiprocessing.get_context("spawn")
    workers = []

    async def receive(connection):
        async with asyncio.timeout(20):
            result = await asyncio.to_thread(connection.recv)
        assert "error" not in result, result
        return result

    async def states(command, live):
        for _, connection in live:
            connection.send(command)
        return await asyncio.gather(*(receive(connection) for _, connection in live))

    async def revision():
        async with database.sessions() as session:
            return await head(session)

    try:
        for _ in range(4):
            parent, child = context.Pipe()
            process = context.Process(
                target=run,
                args=(child, database.url, str(tmp_path / "shared"), fast_policy()),
                daemon=True,
            )
            process.start()
            child.close()
            workers.append((process, parent))
        await asyncio.gather(*(receive(connection) for _, connection in workers))
        statuses = await states(["state"], workers)
        assert sum(status["owner"] for status in statuses) == 1
        identifier = await create_word(database.sessions, "bank")
        statuses = await states(["wait", await revision(), "bank"], workers)
        assert all(status["words"] == [identifier] for status in statuses)
        assert sum(status["applications"] for status in statuses) == 1
        owner = next(i for i, status in enumerate(statuses) if status["owner"])
        process, connection = workers[owner]
        process.kill()
        await asyncio.to_thread(process.join, 5)
        connection.close()
        live = [worker for i, worker in enumerate(workers) if i != owner]
        async with asyncio.timeout(5):
            while True:
                statuses = await states(["state"], live)
                if sum(status["owner"] for status in statuses) == 1:
                    break
                await asyncio.sleep(0.02)
        change = await edit_word(database.sessions, identifier, lemma="lender")
        statuses = await states(["wait", change, "lender"], live)
        assert all(status["words"] == [identifier] for status in statuses)
        change = await delete_word(database.sessions, identifier)
        statuses = await states(["wait", change, "lender"], live)
        assert all(status["words"] == [] for status in statuses)
    finally:
        for process, connection in workers:
            if process.is_alive():
                connection.send(["stop"])
        for process, connection in workers:
            await asyncio.to_thread(process.join, 5)
            if process.is_alive():
                process.terminate()
                await asyncio.to_thread(process.join, 5)
            connection.close()


async def test_transient_bootstrap_database_error_retries_with_same_writer(
    database, tmp_path, monkeypatch
):
    from sqlalchemy.exc import DBAPIError

    index = SearchIndex(database.sessions, str(tmp_path / "index"), policy=fast_policy())
    rebuild = index.rebuild
    attempts = []

    async def temporarily_unavailable(snapshot, writer):
        attempts.append(writer)
        if len(attempts) == 1:
            raise DBAPIError("SELECT", {}, ConnectionError("temporary database failure"))
        await rebuild(snapshot, writer)

    monkeypatch.setattr(index, "rebuild", temporarily_unavailable)
    try:
        await index.start()
        assert len(attempts) == 2 and attempts[0] is attempts[1]
        index.ready()
    finally:
        await index.close()


async def test_publication_timeout_keeps_committed_content_and_releases_database_connections(
    database, tmp_path, monkeypatch
):
    from pycil.infrastructure.content_revisions import replay

    index = SearchIndex(
        database.sessions,
        str(tmp_path / "index"),
        policy=fast_policy().model_copy(update={"publication_timeout_seconds": 0.05}),
    )
    await index.start()
    resume = asyncio.Event()
    synchronize = index.synchronize

    async def paused(writer):
        await resume.wait()
        return await synchronize(writer)

    monkeypatch.setattr(index, "synchronize", paused)
    try:
        word = await create_word(database.sessions, "bank")
        with pytest.raises(RuntimeError, match="awaiting search publication"):
            await index.wait_for_revision(10**9)
        assert database.engine.pool.checkedout() == 0
        async with database.sessions() as session:
            assert (await replay(session, "word", word))["lemma"] == "bank"
        resume.set()
        await index.update(word)
    finally:
        resume.set()
        await index.close()


@pytest.mark.parametrize("after_commit", [False, True])
async def test_sigkill_at_batch_commit_keeps_documents_and_cursor_atomic(
    database, tmp_path, after_commit
):
    import multiprocessing

    from pycil.vocabulary.content import edit_word
    from tests.support.search_worker import run

    word = await create_word(database.sessions, "bank")
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    armed, reached = context.Event(), context.Event()
    directory = str(tmp_path / "index")
    process = context.Process(
        target=run,
        args=(
            child,
            database.url,
            directory,
            fast_policy(),
            (armed, reached, after_commit),
        ),
        daemon=True,
    )
    process.start()
    child.close()
    replica = None
    try:
        async with asyncio.timeout(15):
            assert (await asyncio.to_thread(parent.recv))["ready"]
        armed.set()
        revision = await edit_word(database.sessions, word, lemma="lender")
        assert await asyncio.to_thread(reached.wait, 10)
        process.kill()
        await asyncio.to_thread(process.join, 5)
        replica = SearchIndex(database.sessions, directory, policy=fast_policy())
        # Inspect the durable commit before catch-up: documents and cursor agree.
        replica.snapshot = replica.open()
        cursor = replica.cursor()
        hits = replica.find(replica.snapshot, "lender", False, 10)
        assert (cursor >= revision) is bool(hits)
        await replica.start()
        await replica.wait_for_revision(revision)
        assert (await replica.search("lender")).items[0].word_id == word
    finally:
        if process.is_alive():
            process.terminate()
        await asyncio.to_thread(process.join, 5)
        parent.close()
        if replica is not None:
            await replica.close()
