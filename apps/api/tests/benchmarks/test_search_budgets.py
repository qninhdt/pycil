"""Small declared local workload; timings are evidence, never production SLO assertions."""

import asyncio
import json
import resource
from time import perf_counter

from sqlalchemy import event
from structlog.testing import capture_logs

from pycil.app.config import load_config
from pycil.infrastructure.content_revisions import capture, publish
from pycil.themes.models import Theme
from pycil.vocabulary.enums import EntryType, GenerationState
from pycil.vocabulary.models import Word
from pycil.vocabulary.search import SearchIndex


async def test_default_poll_batch_pool_and_publication_lock_cost(database, tmp_path):
    async with database.sessions() as session, session.begin():
        words = [
            Word(
                lemma=f"entry{i}",
                match_key=f"entry{i}",
                entry_type=EntryType.WORD,
                generation_state=GenerationState.DONE,
            )
            for i in range(100)
        ]
        session.add_all(words)
        await session.flush()
        await publish(session, {("word", word.id): None for word in words})
    index = SearchIndex(database.sessions, str(tmp_path / "index"))
    started = perf_counter()
    cpu_before = resource.getrusage(resource.RUSAGE_SELF)
    await index.start()
    startup_ms = (perf_counter() - started) * 1000
    try:
        queries = []

        def record(*args):
            queries.append(args[2])

        event.listen(database.engine.sync_engine, "before_cursor_execute", record)
        try:
            await asyncio.sleep(load_config().runtime.search.poll_interval_seconds + 0.25)
            idle_queries = len(queries)
            assert database.engine.pool.checkedout() == 0
            async with database.sessions() as session, session.begin():
                before = await capture(session, [("word", word.id) for word in words])
                for word in words:
                    (await session.get(Word, word.id)).lemma = f"changed{word.id}"
                revision = await publish(session, before)
            queries.clear()
            started = perf_counter()
            await index.wait_for_revision(revision)
            visibility_ms = (perf_counter() - started) * 1000
            batch_queries = len(queries)
        finally:
            event.remove(database.engine.sync_engine, "before_cursor_execute", record)
        assert (await index.search(f"changed{words[0].id}")).items[0].word_id == words[0].id
        assert database.engine.pool.checkedout() == 0
        gate = asyncio.Barrier(20)

        async def publish_theme(i):
            await gate.wait()
            async with database.sessions() as session, session.begin():
                theme = Theme(key=f"theme{i}", name=f"Theme {i}", voice="plain", diction="simple")
                session.add(theme)
                await session.flush()
                await publish(session, {("theme", theme.id): None})

        with capture_logs() as logs:
            await asyncio.gather(*(publish_theme(i) for i in range(20)))
        waits = sorted(row["wait_ms"] for row in logs if row["event"] == "content_publication_lock")
        assert len(waits) == 20
        cpu_after = resource.getrusage(resource.RUSAGE_SELF)
        print(
            "SEARCH_BUDGET "
            + json.dumps(
                {
                    "workload": (
                        "100 minimal DONE words, one 100-word edit batch, 20 concurrent themes"
                    ),
                    "startup_ms": round(startup_ms, 2),
                    "visibility_ms": round(visibility_ms, 2),
                    "idle_queries_over_one_poll": idle_queries,
                    "batch_queries": batch_queries,
                    "pool_checked_out_after_work": database.engine.pool.checkedout(),
                    "publication_lock_wait_p50_ms": waits[len(waits) // 2],
                    "lock_wait_max_ms": waits[-1],
                    "process_cpu_seconds": round(
                        cpu_after.ru_utime
                        + cpu_after.ru_stime
                        - cpu_before.ru_utime
                        - cpu_before.ru_stime,
                        3,
                    ),
                    "completed_index_bytes": sum(
                        path.stat().st_size
                        for path in (tmp_path / "index").rglob("*")
                        if path.is_file()
                    ),
                }
            )
        )
    finally:
        await index.close()
