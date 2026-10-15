import asyncio
from contextlib import AsyncExitStack

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from psycopg_pool import PoolTimeout
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from pycil.app.config import load_config
from pycil.assistant.checkpoints import checkpoint_pool
from pycil.infrastructure import observability
from pycil.infrastructure.database import connect


@pytest.fixture
def database_metrics(monkeypatch):
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    meter = provider.get_meter("pycil.database")
    monkeypatch.setattr(
        observability,
        "_database_histograms",
        {
            operation: meter.create_histogram(f"pycil.db.{operation}.duration", unit="s")
            for operation in ("pool.acquire", "query")
        },
    )
    try:
        yield reader
    finally:
        provider.shutdown()


def points(reader, operation, pool="application", outcome="succeeded"):
    data = reader.get_metrics_data()
    return [
        point
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == f"pycil.db.{operation}.duration" and metric.unit == "s"
        for point in metric.data.data_points
        if point.attributes == {"pool": pool, "outcome": outcome}
    ]


async def test_application_pool_rejects_excess_checkout_and_recovers(database, database_metrics):
    policy = load_config().runtime.database.application_pool
    engine, _sessions = connect(database.url, **policy.model_dump())
    try:
        async with AsyncExitStack() as held:
            for _ in range(policy.size + policy.max_overflow):
                await held.enter_async_context(engine.connect())
            with pytest.raises(SQLAlchemyTimeoutError):
                async with engine.connect():
                    pytest.fail("Exhausted application pool accepted another checkout")
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT 1")) == 1
        failed = points(database_metrics, "pool.acquire", outcome="failed")
        assert len(failed) == 1 and failed[0].count == 1
        assert failed[0].sum >= policy.timeout_seconds
    finally:
        await engine.dispose()


async def test_checkpoint_pool_caps_checkout_preserves_native_settings_and_recovers(
    database, database_metrics
):
    policy = load_config().runtime.database.checkpoint_pool.model_copy(
        update={"timeout_seconds": 0.1}
    )
    async with checkpoint_pool(database.url, **policy.model_dump()) as pool:
        async with AsyncExitStack() as held:
            for _ in range(policy.max_size):
                connection = await held.enter_async_context(pool.connection())
                assert connection.autocommit
                assert connection.prepare_threshold == 0
            with pytest.raises(PoolTimeout):
                async with pool.connection():
                    pytest.fail("Exhausted checkpoint pool accepted another checkout")
        async with pool.connection() as connection:
            result = await connection.execute("SELECT 1 AS value")
            assert await result.fetchone() == {"value": 1}
        failed = points(database_metrics, "pool.acquire", pool="checkpoint", outcome="failed")
        assert len(failed) == 1 and failed[0].count == 1
        assert failed[0].sum >= policy.timeout_seconds


@pytest.mark.parametrize("pool_name", ["application", "checkpoint"])
async def test_connection_and_pool_startup_timeouts_bound_unresponsive_database(pool_name):
    handlers = set()
    release = asyncio.Event()
    accepted = asyncio.Event()

    async def hold_connection(reader, writer):
        handlers.add(asyncio.current_task())
        accepted.set()
        try:
            # Native pool timeout joins connection workers before raising PoolTimeout.
            await asyncio.wait_for(release.wait(), timeout=0.2)
        except TimeoutError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(hold_connection, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    url = f"postgresql+asyncpg://test:test@127.0.0.1:{port}/test"
    try:
        async with asyncio.timeout(3):
            if pool_name == "application":
                policy = load_config().runtime.database.application_pool.model_copy(
                    update={"connect_timeout_seconds": 0.05}
                )
                engine, _sessions = connect(url, **policy.model_dump())
                try:
                    with pytest.raises(asyncio.TimeoutError):
                        async with engine.connect():
                            pytest.fail("Unresponsive database accepted a connection")
                finally:
                    await engine.dispose()
            else:
                policy = load_config().runtime.database.checkpoint_pool.model_copy(
                    update={"startup_timeout_seconds": 0.05}
                )
                with pytest.raises(PoolTimeout):
                    async with checkpoint_pool(url, **policy.model_dump()):
                        pytest.fail("Unresponsive database initialized the pool")
            assert accepted.is_set()
    finally:
        server.close()
        release.set()
        await asyncio.gather(*handlers)
        await server.wait_closed()


async def test_pool_wait_is_measured_before_query_execution(database, database_metrics):
    engine, sessions = connect(database.url, size=1, timeout_seconds=2)
    attempting = asyncio.Event()

    async def read():
        async with sessions() as session:
            attempting.set()
            return await session.scalar(text("SELECT 1"))

    try:
        async with asyncio.timeout(5), asyncio.TaskGroup() as tasks:
            async with engine.connect():
                waiting = tasks.create_task(read())
                await attempting.wait()
                await asyncio.sleep(0.05)
                assert not waiting.done()
                assert points(database_metrics, "query") == []
        assert waiting.result() == 1
        acquisitions = points(database_metrics, "pool.acquire")
        queries = points(database_metrics, "query")
        assert len(acquisitions) == 1 and acquisitions[0].count == 2
        assert acquisitions[0].max >= 0.05
        assert len(queries) == 1 and queries[0].count == 1
    finally:
        await engine.dispose()


@pytest.mark.parametrize("cancel", [False, True])
async def test_query_metrics_preserve_errors_and_cancellation(database, database_metrics, cancel):
    engine, _sessions = connect(database.url)
    try:
        async with engine.connect() as connection:
            if cancel:
                with pytest.raises(asyncio.TimeoutError):
                    async with asyncio.timeout(0.05):
                        await connection.execute(text("SELECT pg_sleep(5)"))
            else:
                with pytest.raises(DBAPIError):
                    await connection.execute(text("SELECT 1 / 0"))
        outcome = "cancelled" if cancel else "failed"
        failed = points(database_metrics, "query", outcome=outcome)
        assert len(failed) == 1 and failed[0].count == 1
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT 1")) == 1
        assert points(database_metrics, "query")[0].count == 1
    finally:
        await engine.dispose()


@pytest.mark.parametrize("pool_name", ["application", "checkpoint"])
async def test_cancelled_checkout_is_recorded_and_pool_recovers(
    database, database_metrics, pool_name
):
    async with AsyncExitStack() as resources:
        if pool_name == "application":
            engine, _sessions = connect(database.url, size=1)
            resources.push_async_callback(engine.dispose)
            acquire = engine.connect
        else:
            pool = await resources.enter_async_context(
                checkpoint_pool(database.url, min_size=1, max_size=1)
            )
            acquire = pool.connection
        async with acquire():
            with pytest.raises(asyncio.TimeoutError):
                async with asyncio.timeout(0.05), acquire():
                    pytest.fail("Exhausted pool accepted another checkout")
        cancelled = points(database_metrics, "pool.acquire", pool=pool_name, outcome="cancelled")
        assert len(cancelled) == 1 and cancelled[0].count == 1
        async with acquire():
            pass
