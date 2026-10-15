import asyncio
import json
import logging
from functools import partial
from types import SimpleNamespace

import pytest
import structlog
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from opentelemetry import trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from psycopg import errors, sql
from sqlalchemy import event, text

from pycil.app import http
from pycil.app.config import load_config
from pycil.app.factory import create_app
from pycil.assistant import checkpoints
from pycil.assistant.checkpoints import checkpoint_pool
from pycil.infrastructure import database as database_module
from pycil.infrastructure.database import connect
from tests.support.vocabulary import neutral_word


@pytest.fixture
async def database_telemetry(database, monkeypatch, capsys):
    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    exporter = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(database_module, "_query_tracer", provider.get_tracer("pycil.database"))
    monkeypatch.setattr(checkpoints, "_query_tracer", provider.get_tracer("pycil.checkpoints"))
    monkeypatch.setattr(
        http,
        "OpenTelemetryMiddleware",
        partial(http.OpenTelemetryMiddleware, tracer_provider=provider, meter_provider=meter),
    )
    engine, sessions = connect(database.url, size=1)
    logging_state = logging.getLogger().handlers[:], logging.getLogger().level
    structlog_state = structlog.get_config()
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT 1")) == 1
        assert provider.force_flush()
        exporter.clear()
        yield SimpleNamespace(
            engine=engine,
            sessions=sessions,
            exporter=exporter,
            provider=provider,
            reader=reader,
            tracer=provider.get_tracer("controlled-work"),
        )
    finally:
        logging.getLogger().handlers, logging.getLogger().level = logging_state
        structlog.configure(**structlog_state)
        await engine.dispose()
        provider.shutdown()
        meter.shutdown()


async def test_real_word_read_has_one_safe_child_span_per_statement(
    database, database_telemetry, capsys
):
    signals = database_telemetry
    word_id, _ = await neutral_word(database.sessions)
    assert signals.provider.force_flush()
    signals.exporter.clear()
    statements = []

    @event.listens_for(signals.engine.sync_engine, "before_cursor_execute")
    def executed(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    app = create_app()
    app.state.config = load_config()
    app.state.deployment = SimpleNamespace(allowed_origins=[])
    app.state.sessions = signals.sessions
    app.state.word_cache = app.state.sense_cache = None

    @app.get("/controlled/sql/{mode}")
    async def query(mode: int):
        statement = (
            "SELECT 'private-literal'::text /* private-comment */",
            "SELECT CAST(:value AS integer)",
            "private-operation",
        )[mode]
        async with signals.sessions() as session:
            value = await session.scalar(text(statement), {"value": "private-bind"})
        return {"value": value}

    capsys.readouterr()
    async with AsyncClient(transport=ASGITransport(app), base_url="http://api.test") as client:
        response = await client.get(f"/v1/words/{word_id}")
        assert response.status_code == 200 and response.json()["lemma"] == "bank"
        assert len(statements) == 1
        response = await client.get("/controlled/sql/0")
        assert response.status_code == 200 and response.json() == {"value": "private-literal"}
        for mode in (1, 2):
            response = await client.get(f"/controlled/sql/{mode}")
            assert response.status_code == 500
            assert response.json()["code"] == "internal_error"
    assert signals.provider.force_flush()
    spans = signals.exporter.get_finished_spans()
    servers = [span for span in spans if span.kind == trace.SpanKind.SERVER]
    queries = [span for span in spans if span.kind == trace.SpanKind.CLIENT]
    assert len(queries) == len(statements) == len(servers) == 4
    for span in queries:
        parent = next(
            server for server in servers if server.context.trace_id == span.context.trace_id
        )
        assert span.parent.span_id == parent.context.span_id
        assert span.context.span_id != parent.context.span_id
        assert span.attributes["db.system.name"] == "postgresql"
        assert span.attributes["db.operation.name"] == span.name
        assert set(span.attributes) <= {"db.system.name", "db.operation.name", "error.type"}
        assert parent.start_time <= span.start_time <= span.end_time <= parent.end_time
        assert not span.status.description and not span.events
    assert sum(span.status.status_code == trace.StatusCode.ERROR for span in queries) == 2
    assert {span.name for span in queries} == {"SELECT", "SQL"}
    logs = capsys.readouterr().out
    completions = [
        json.loads(line) for line in logs.splitlines() if "http_request_completed" in line
    ]
    assert len(completions) == 4
    assert {e["trace_id"] for e in completions} == {f"{s.context.trace_id:032x}" for s in servers}
    metrics = signals.reader.get_metrics_data()
    payload = str([span.to_json() for span in spans]) + str(metrics) + logs
    assert "private-" not in payload
    assert "financial institution" not in payload
    assert "db.statement" not in payload and "db.query.text" not in payload


async def test_checkout_wait_precedes_query_span(database_telemetry):
    signals = database_telemetry
    attempting = asyncio.Event()

    async def read():
        with signals.tracer.start_as_current_span("controlled-read"):
            attempting.set()
            async with signals.sessions() as session:
                return await session.scalar(text("SELECT 1"))

    async with asyncio.timeout(5), asyncio.TaskGroup() as tasks:
        async with signals.engine.connect():
            waiting = tasks.create_task(read())
            await attempting.wait()
            await asyncio.sleep(0.05)
            assert not waiting.done()
            assert signals.provider.force_flush()
            assert not any(s.name == "SELECT" for s in signals.exporter.get_finished_spans())
    assert waiting.result() == 1
    assert signals.provider.force_flush()
    spans = signals.exporter.get_finished_spans()
    parent = next(span for span in spans if span.name == "controlled-read")
    queries = [span for span in spans if span.name == "SELECT"]
    assert len(queries) == 1
    assert queries[0].start_time - parent.start_time >= 50_000_000
    assert queries[0].parent.span_id == parent.context.span_id


async def test_cancelled_query_span_ends_and_connection_recovers(database_telemetry):
    signals = database_telemetry
    with signals.tracer.start_as_current_span("controlled-cancel"):
        async with signals.sessions() as session:
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.05):
                    await session.execute(text("SELECT pg_sleep(5) /* private-cancel */"))
    async with signals.sessions() as session:
        assert await session.scalar(text("SELECT 1")) == 1
    assert signals.provider.force_flush()
    queries = [span for span in signals.exporter.get_finished_spans() if span.name == "SELECT"]
    assert len(queries) == 2
    assert queries[0].status.status_code == trace.StatusCode.ERROR
    assert queries[0].end_time is not None
    assert queries[1].status.status_code != trace.StatusCode.ERROR
    assert "private-" not in str([span.to_json() for span in queries])


async def test_checkpoint_native_persistence_has_safe_http_child_spans(
    database, database_telemetry, capsys
):
    signals = database_telemetry
    app = create_app()
    app.state.config = load_config()
    app.state.deployment = SimpleNamespace(allowed_origins=[])
    async with checkpoint_pool(database.url) as pool:
        # Finish pool initialization outside the request under observation.
        async with pool.connection() as connection:
            assert connection.autocommit and connection.prepare_threshold == 0
        saver = AsyncPostgresSaver(pool)

        @app.post("/controlled/checkpoint")
        async def persist():
            checkpoint = empty_checkpoint()
            checkpoint["channel_values"] = {"messages": ["private-conversation"]}
            checkpoint["channel_versions"] = {"messages": "1"}
            config = await saver.aput(
                {"configurable": {"thread_id": "private-thread", "checkpoint_ns": ""}},
                checkpoint,
                {"source": "input", "step": 0, "parents": {}, "note": "private-metadata"},
                {"messages": "1"},
            )
            await saver.aput_writes(config, [("pending", "private-write")], "private-task")
            stored = await saver.aget_tuple(config)
            assert stored.checkpoint["channel_values"] == checkpoint["channel_values"]
            assert stored.pending_writes == [("private-task", "pending", "private-write")]
            await saver.adelete_thread("private-thread")
            assert await saver.aget_tuple(config) is None
            return {"status": "stored-and-deleted"}

        signals.exporter.clear()
        capsys.readouterr()
        async with AsyncClient(transport=ASGITransport(app), base_url="http://api.test") as client:
            response = await client.post("/controlled/checkpoint")
        assert response.status_code == 200 and response.json() == {"status": "stored-and-deleted"}
    assert signals.provider.force_flush()
    spans = signals.exporter.get_finished_spans()
    server = next(span for span in spans if span.kind == trace.SpanKind.SERVER)
    queries = [span for span in spans if span.kind == trace.SpanKind.CLIENT]
    # One span per native execute/executemany call, including the batched blob/write operations.
    assert len(queries) == 8
    assert [span.name for span in queries].count("INSERT") == 3
    assert [span.name for span in queries].count("SELECT") == 2
    assert [span.name for span in queries].count("DELETE") == 3
    for span in queries:
        assert span.context.trace_id == server.context.trace_id
        assert span.parent.span_id == server.context.span_id
        assert span.instrumentation_scope.name == "pycil.checkpoints"
        assert span.attributes == {
            "db.system.name": "postgresql",
            "db.operation.name": span.name,
            "pycil.db.pool": "checkpoint",
            "pycil.db.execution.mode": "direct" if span.name == "SELECT" else "pipeline",
        }
        assert server.start_time <= span.start_time <= span.end_time <= server.end_time
        assert not span.status.description and not span.events
    payload = str([span.to_json() for span in spans]) + capsys.readouterr().out
    assert "private-" not in payload
    assert "db.statement" not in payload and "db.query.text" not in payload


async def test_checkpoint_query_failures_and_cancellation_preserve_driver_and_privacy(
    database, database_telemetry
):
    signals = database_telemetry
    async with checkpoint_pool(database.url, min_size=1, max_size=1) as pool:
        signals.exporter.clear()
        with signals.tracer.start_as_current_span("controlled-checkpoint") as parent:
            async with pool.connection() as connection:
                with pytest.raises(errors.InvalidTextRepresentation):
                    await connection.execute("SELECT CAST(%s AS integer)", ("private-bind",))
                with pytest.raises(errors.SyntaxError):
                    await connection.execute("private-operation")
                with pytest.raises(TimeoutError):
                    async with asyncio.timeout(0.05):
                        await connection.execute("SELECT pg_sleep(5) /* private-cancel */")
                cursor = await connection.execute(
                    sql.SQL("SELECT {} AS value").format(sql.Literal(7))
                )
                assert await cursor.fetchone() == {"value": 7}
                cursor = await connection.execute(b"SELECT 8 AS value")
                assert await cursor.fetchone() == {"value": 8}
        async with pool.connection() as connection:
            cursor = await connection.execute("SELECT 1 AS value")
            assert await cursor.fetchone() == {"value": 1}
    assert signals.provider.force_flush()
    spans = signals.exporter.get_finished_spans()
    queries = [span for span in spans if span.kind == trace.SpanKind.CLIENT]
    assert len(queries) == 6
    assert [span.name for span in queries] == ["SELECT", "SQL", "SELECT", "SQL", "SQL", "SELECT"]
    for span in queries[:5]:
        assert span.context.trace_id == parent.get_span_context().trace_id
        assert span.parent.span_id == parent.get_span_context().span_id
        assert span.end_time is not None
        assert not span.events and not span.status.description
    assert [span.attributes["error.type"] for span in queries[:3]] == [
        "InvalidTextRepresentation",
        "SyntaxError",
        "CancelledError",
    ]
    assert all(span.status.status_code == trace.StatusCode.ERROR for span in queries[:3])
    assert all(span.status.status_code != trace.StatusCode.ERROR for span in queries[3:])
    assert "private-" not in str([span.to_json() for span in spans])


async def test_checkpoint_checkout_wait_precedes_query_span(database, database_telemetry):
    signals = database_telemetry
    attempting = asyncio.Event()
    async with checkpoint_pool(database.url, min_size=1, max_size=1) as pool:

        async def read():
            with signals.tracer.start_as_current_span("controlled-checkpoint-wait"):
                attempting.set()
                async with pool.connection() as connection:
                    cursor = await connection.execute("SELECT 1 AS value")
                    return await cursor.fetchone()

        signals.exporter.clear()
        async with asyncio.timeout(5), asyncio.TaskGroup() as tasks:
            async with pool.connection():
                waiting = tasks.create_task(read())
                await attempting.wait()
                await asyncio.sleep(0.05)
                assert not waiting.done()
                assert not signals.exporter.get_finished_spans()
        assert waiting.result() == {"value": 1}
    assert signals.provider.force_flush()
    spans = signals.exporter.get_finished_spans()
    parent = next(span for span in spans if span.name == "controlled-checkpoint-wait")
    queries = [span for span in spans if span.kind == trace.SpanKind.CLIENT]
    assert len(queries) == 1
    assert queries[0].start_time - parent.start_time >= 50_000_000
    assert queries[0].parent.span_id == parent.context.span_id


async def test_checkpoint_pipeline_keeps_native_sync_failure(database, database_telemetry):
    signals = database_telemetry
    async with checkpoint_pool(database.url, min_size=1, max_size=1) as pool:
        signals.exporter.clear()
        async with pool.connection() as connection:
            with pytest.raises(errors.InvalidTextRepresentation):
                async with connection.pipeline():
                    await connection.execute("SELECT CAST(%s AS integer)", ("private-pipeline",))
            cursor = await connection.execute("SELECT 1 AS value")
            assert await cursor.fetchone() == {"value": 1}
    assert signals.provider.force_flush()
    queries = [s for s in signals.exporter.get_finished_spans() if s.kind == trace.SpanKind.CLIENT]
    assert len(queries) == 2 and all(s.end_time is not None for s in queries)
    assert queries[0].attributes["pycil.db.execution.mode"] == "pipeline"
    assert queries[1].attributes["pycil.db.execution.mode"] == "direct"
    assert "private-" not in str([span.to_json() for span in queries])
