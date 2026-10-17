import asyncio

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from pycil.app.config import load_config
from pycil.observability import search as observation
from pycil.vocabulary.content import edit_word
from pycil.vocabulary.enums import EntryType, GenerationState
from pycil.vocabulary.errors import InvalidResourceError
from pycil.vocabulary.models import Word
from pycil.vocabulary.revisions import publish


@pytest.fixture
async def observed_index(database, monkeypatch, tmp_path):
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    provider.get_meter("pycil.search").create_observable_gauge(
        "pycil.search.pending_age", callbacks=[observation._pending_ages], unit="s"
    )
    monkeypatch.setattr(
        observation,
        "_duration",
        provider.get_meter("pycil.search").create_histogram("pycil.search.duration", unit="s"),
    )
    config = load_config().vocabulary
    index = observation.ObservedSearchIndex(
        database.sessions,
        str(tmp_path / "index"),
        name="dictionary",
        policy=config.search_runtime.model_copy(
            update={"poll_interval_seconds": 0.01, "retry_jitter_seconds": 0}
        ),
        query_policy=config.search,
    )

    def count(operation, outcome):
        data = reader.get_metrics_data()
        points = [
            point
            for resource in data.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
            if metric.name == "pycil.search.duration"
            for point in metric.data.data_points
        ]
        assert "private-" not in str(data)
        assert all(set(point.attributes) == {"index", "operation", "outcome"} for point in points)
        assert all(point.sum >= 0 for point in points)
        return sum(
            point.count
            for point in points
            if point.attributes
            == {"index": "dictionary", "operation": operation, "outcome": outcome}
        )

    def pending_age():
        data = reader.get_metrics_data()
        points = [
            point
            for resource in data.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
            if metric.name == "pycil.search.pending_age"
            for point in metric.data.data_points
        ]
        assert all(point.attributes == {"index": "dictionary"} for point in points)
        return [point.value for point in points]

    try:
        await index.start()
        yield index, count, pending_age
    finally:
        await index.close()
        provider.shutdown()


async def test_query_keeps_reading_committed_snapshot_during_synchronization(
    database, observed_index, monkeypatch
):
    index, count, pending_age = observed_index
    assert pending_age() == [0]
    entered, resume = asyncio.Event(), asyncio.Event()
    projection = index.projection

    async def paused_projection(*args, **kwargs):
        entered.set()
        await resume.wait()
        return await projection(*args, **kwargs)

    monkeypatch.setattr(index, "projection", paused_projection)
    async with database.sessions() as session, session.begin():
        word = Word(
            lemma="bank",
            match_key="bank",
            entry_type=EntryType.WORD,
            generation_state=GenerationState.DONE,
        )
        session.add(word)
        await session.flush()
        revision = await publish(session, {word.id: None})
    try:
        async with asyncio.timeout(5):
            await entered.wait()
            assert not (await index.search("bank")).items
            assert not (await index.search("private-query")).items
        statements = []

        def executed(*args):
            statements.append(args[2])

        event.listen(database.engine.sync_engine, "before_cursor_execute", executed)
        try:
            age = pending_age()[0]
            assert age > 0
            clock = observation.perf_counter
            with monkeypatch.context() as patch:
                patch.setattr(observation, "perf_counter", lambda: clock() + 30)
                assert pending_age()[0] >= age + 30
            assert not statements  # Collection only reads the last poll's in-memory state.
        finally:
            event.remove(database.engine.sync_engine, "before_cursor_execute", executed)

        async def failed_poll(*args):
            raise OperationalError("private-statement", None, RuntimeError("private-error"))

        with monkeypatch.context() as patch:
            patch.setattr(observation.SearchIndex, "pending_revisions", failed_poll)
            async with database.sessions() as session:
                with pytest.raises(OperationalError):
                    await index.pending_revisions(session, index.cursor())
            assert pending_age()[0] >= age
        assert count("query", "succeeded") == 2
    finally:
        resume.set()
    await index.wait_for_revision(revision)
    assert (await index.search("bank")).items[0].word_id == word.id
    assert count("rebuild", "succeeded") == 1
    assert count("synchronize", "succeeded") >= 1
    assert count("synchronize", "idle") >= 1
    assert count("publication_wait", "succeeded") == 1
    async with asyncio.timeout(5):
        while pending_age() != [0]:
            await asyncio.sleep(0.01)
    with pytest.raises(InvalidResourceError):
        await index.search("")
    assert count("query", "rejected") == 1


async def test_failed_publication_and_recovery_have_separate_outcomes(
    database, observed_index, monkeypatch
):
    index, count, pending_age = observed_index
    async with database.sessions() as session, session.begin():
        word = Word(
            lemma="bank",
            match_key="bank",
            entry_type=EntryType.WORD,
            generation_state=GenerationState.DONE,
        )
        session.add(word)
        await session.flush()
        revision = await publish(session, {word.id: None})
    await index.wait_for_revision(revision)
    documents = index.documents

    def failure(*args):
        yield from documents(*args)
        raise RuntimeError("private-publication-failure")

    monkeypatch.setattr(index, "documents", failure)
    await edit_word(database.sessions, word.id, lemma="lender")
    async with asyncio.timeout(5):
        while index.failure is None:
            await asyncio.sleep(0.01)
    assert count("synchronize", "failed") == 1
    assert count("query", "failed") == 0
    with pytest.raises(RuntimeError, match="search index is unavailable"):
        await index.search("private-query")
    assert count("query", "failed") == 1
    await index.close()
    assert pending_age() == []
    monkeypatch.setattr(index, "documents", documents)
    await index.start()
    assert (await index.search("lender")).items[0].word_id == word.id
    assert count("rebuild", "succeeded") == 1
    waiting = asyncio.create_task(index.wait_for_revision(index.cursor() + 1))
    await asyncio.sleep(0)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert count("publication_wait", "cancelled") == 1


async def test_only_shared_directory_owner_emits_backlog_age(observed_index):
    owner, _, pending_age = observed_index
    standby = observation.ObservedSearchIndex(
        owner.sessions,
        owner.path,
        name="dictionary",
        policy=owner.policy,
        query_policy=owner.query_policy,
    )
    try:
        await standby.start()
        assert owner.is_owner and not standby.is_owner
        assert pending_age() == [0]
        await owner.close()
        async with asyncio.timeout(5):
            while not standby.is_owner or not standby._pending_observed:
                await asyncio.sleep(0.01)
        assert pending_age() == [0]
    finally:
        await standby.close()
    assert pending_age() == []
