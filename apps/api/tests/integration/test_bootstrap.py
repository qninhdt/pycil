import asyncio
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TypedDict

import httpx
import pytest
from alembic import command
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from pycil import dependencies
from pycil.account.models import User
from pycil.config import Deployment
from pycil.database import verify_schema
from pycil.dependencies import Session, process_resources
from pycil.main import create_app
from pycil.migrate import migrate, migration_config


def forbid_setup(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("Runtime startup must never migrate/checkpoint setup")

    monkeypatch.setattr(AsyncPostgresSaver, "setup", forbidden)


async def test_migration_gate_rejects_checkpoint_version_gap(database):
    engine, _, url = database
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM checkpoints.checkpoint_migrations WHERE v=1"))
    with pytest.raises(RuntimeError, match="checkpoint_version_mismatch"):
        await asyncio.to_thread(migrate, url)


async def test_migration_gate_separates_all_three_schema_owners(database):
    engine, _, url = database
    async with engine.connect() as connection:
        owners = (
            await connection.execute(
                text(
                    "SELECT schemaname, tablename FROM pg_tables "
                    "WHERE schemaname IN ('public','lexi','checkpoints')"
                )
            )
        ).all()
        assert ("checkpoints", "checkpoint_migrations") in owners
        assert ("checkpoints", "checkpoints") in owners
        assert not any(
            name.startswith("checkpoint") and schema != "checkpoints" for schema, name in owners
        )
        assert ("lexi", "senses") in owners
        assert ("public", "users") in owners
    # A lossy placement downgrade is explicitly blocked; external schemas stay intact.
    with pytest.raises(RuntimeError, match="pre-upgrade backup"):
        await asyncio.to_thread(command.downgrade, migration_config(url), "base")
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT to_regclass('public.users')")) is not None
        assert (
            await connection.scalar(text("SELECT version_num FROM lexi.alembic_version"))
            == "20261003_base"
        )
        assert await connection.scalar(
            text("SELECT count(*) FROM checkpoints.checkpoint_migrations")
        ) == len(AsyncPostgresSaver.MIGRATIONS)
    await asyncio.to_thread(command.upgrade, migration_config(url), "head")
    await verify_schema(engine)
    await asyncio.to_thread(command.check, migration_config(url))


@pytest.mark.parametrize("database", ["0001_baseline"], indirect=True)
async def test_fresh_baseline_refuses_existing_public_data_without_reset(database):
    engine, _, url = database
    await asyncio.to_thread(command.downgrade, migration_config(url), "base")
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE public.protected_marker(value text)"))
        await connection.execute(text("INSERT INTO public.protected_marker VALUES ('keep')"))
    with pytest.raises(RuntimeError, match="empty public schema"):
        await asyncio.to_thread(migrate, url)
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT value FROM public.protected_marker")) == "keep"
        assert await connection.scalar(text("SELECT to_regclass('public.users')")) is None
        assert (
            await connection.scalar(text("SELECT version_num FROM lexi.alembic_version"))
            == "20261003_base"
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE public.alembic_version SET version_num='unknown'",
        "UPDATE lexi.alembic_version SET version_num='unknown'",
        "DELETE FROM checkpoints.checkpoint_migrations WHERE v=9",
        "DROP TABLE checkpoints.checkpoint_writes",
        "DROP TABLE public.conversations",
    ],
)
async def test_startup_rejects_drift_without_repair(database, deployment, config, mutation):
    engine, _, _ = database
    async with engine.begin() as connection:
        await connection.execute(text(mutation))
    with pytest.raises(RuntimeError, match="Runtime initialization failed") as caught:
        async with process_resources(config, deployment):
            pytest.fail("Drifted database must not start")
    assert deployment.db_url.get_secret_value() not in str(caught.value)
    with pytest.raises((SQLAlchemyError, RuntimeError)):
        await verify_schema(engine)


async def test_native_resources_close_after_lifespan_and_restart(
    database, deployment, config, monkeypatch, no_inference
):
    forbid_setup(monkeypatch)
    monkeypatch.setattr("pycil.main.load_config", lambda: config)
    monkeypatch.setattr(Deployment, "from_environment", classmethod(lambda cls: deployment))
    app = create_app()
    saved = []
    for _ in range(2):
        async with app.router.lifespan_context(app):
            resource = app.state.lexicon
            refresh = resource._refresh_task
            assert refresh is not None and not refresh.done()
            saved.append(resource)
            http = app.state.http
            pool = app.state.checkpoint_pool
            redis = app.state.redis
            assert not pool.closed
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                assert (await client.get("/health")).status_code == 200
                assert (await client.get("/ready")).status_code == 200
                # Native stored reads need no model initialization.
                assert await resource.get_word(987654) is None
                response = await client.get("/health", headers={"Origin": "https://client.invalid"})
                assert response.headers["access-control-allow-origin"] == "https://client.invalid"
                assert response.headers["x-request-id"]
        assert http.is_closed
        assert refresh.done()
        assert pool.closed
        assert not redis.connection_pool._in_use_connections
        assert not any(c.is_connected for c in redis.connection_pool._available_connections)
        assert not hasattr(app.state, "lexicon")
        assert not hasattr(app.state, "product")
        with pytest.raises(RuntimeError):
            await resource.get_word(987654)
    assert saved[0] is not saved[1]


class Counter(TypedDict):
    visits: int


async def test_native_checkpoint_survives_process_restart_without_setup(
    deployment, config, monkeypatch, no_inference
):
    forbid_setup(monkeypatch)
    graph = StateGraph(Counter)
    graph.add_node("increment", lambda state: {"visits": state["visits"] + 1})
    graph.add_edge(START, "increment")
    graph.add_edge("increment", END)
    thread = {"configurable": {"thread_id": "phase2-native-checkpoint"}}
    async with process_resources(config, deployment) as resources:
        agent = graph.compile(checkpointer=AsyncPostgresSaver(resources.checkpoint_pool))
        assert await agent.ainvoke({"visits": 0}, thread) == {"visits": 1}
    async with process_resources(config, deployment) as resources:
        saver = AsyncPostgresSaver(resources.checkpoint_pool)
        agent = graph.compile(checkpointer=saver)
        assert (await agent.aget_state(thread)).values == {"visits": 1}
        assert await agent.ainvoke(None, thread) == {"visits": 1}
        # Native per-thread cleanup, not a second persistence implementation.
        await saver.adelete_thread(thread["configurable"]["thread_id"])
        assert await saver.aget(thread) is None


async def test_request_session_rolls_back_on_failure(
    database, deployment, config, monkeypatch, no_inference
):
    monkeypatch.setattr("pycil.main.load_config", lambda: config)
    monkeypatch.setattr(Deployment, "from_environment", classmethod(lambda cls: deployment))
    app = create_app()

    @app.post("/fail-write")
    async def fail_write(session: Session):
        session.add(User(clerk_subject="rollback-only", settings={}))
        await session.flush()
        raise RuntimeError("private-database-error")

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/fail-write")
        assert response.status_code == 500
        assert response.json() == {"error": "internal_error"}
        async with app.state.sessions() as session:
            assert await session.scalar(text("SELECT count(*) FROM users")) == 0


async def test_partial_startup_failure_closes_already_acquired_resources(
    deployment, config, monkeypatch
):
    opened = {}
    real_connect = dependencies.connect
    real_redis = dependencies.Redis.from_url

    def connect(url):
        engine, sessions = real_connect(url)
        opened["engine"] = engine
        return engine, sessions

    def redis(url, **kwargs):
        client = real_redis(url, **kwargs)
        opened["redis"] = client
        return client

    @asynccontextmanager
    async def fail(url):
        raise RuntimeError("provider-secret-must-not-leak")
        yield

    monkeypatch.setattr(dependencies, "connect", connect)
    monkeypatch.setattr(dependencies.Redis, "from_url", redis)
    monkeypatch.setattr(dependencies, "checkpoint_pool", fail)
    with pytest.raises(RuntimeError, match="Runtime initialization failed") as caught:
        async with process_resources(config, deployment):
            pytest.fail("Acquisition must fail")
    assert "provider-secret-must-not-leak" not in str(caught.value)
    assert opened["engine"].pool.checkedout() == 0
    assert not opened["redis"].connection_pool._in_use_connections
    assert not any(c.is_connected for c in opened["redis"].connection_pool._available_connections)


async def test_cancelled_process_closes_resources_without_swallowing_cancellation(
    deployment, config, no_inference
):
    ready = asyncio.Event()
    owned = {}

    async def process():
        async with process_resources(config, deployment) as resources:
            owned.update(vars(resources))
            ready.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(process())
    await asyncio.wait_for(ready.wait(), timeout=10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert owned["http"].is_closed
    assert owned["checkpoint_pool"].closed
    assert owned["engine"].pool.checkedout() == 0
    assert not owned["redis"].connection_pool._in_use_connections


async def test_cleanup_failure_is_redacted_and_other_resources_still_close(
    deployment, config, monkeypatch, no_inference
):
    real_close = dependencies.Lexicon.close
    owned = {}

    async def close_then_fail(lexicon):
        await real_close(lexicon)
        raise RuntimeError("sensitive-shutdown-error")

    monkeypatch.setattr(dependencies.Lexicon, "close", close_then_fail)
    with pytest.raises(RuntimeError, match="Runtime resource cleanup failed") as caught:
        async with process_resources(config, deployment) as resources:
            owned.update(vars(resources))
    assert "sensitive-shutdown-error" not in str(caught.value)
    assert owned["http"].is_closed
    assert owned["checkpoint_pool"].closed
    assert owned["engine"].pool.checkedout() == 0
    assert not owned["redis"].connection_pool._in_use_connections


async def test_real_disposable_redis_namespace_has_atomic_expiring_keys(
    redis_namespace, config, monkeypatch, caplog
):
    from pydantic import BaseModel

    from pycil.cache import STORE, RedisCache

    class Value(BaseModel):
        name: str

    client, key = redis_namespace
    assert await client.ping()
    assert await client.set(key, "owner-one", nx=True, ex=60)
    assert not await client.set(key, "owner-two", nx=True, ex=60)
    assert await client.get(key) == b"owner-one"
    assert 0 < await client.ttl(key) <= 60
    policy = config.cache.model_copy(update={"max_entries": 2, "max_value_bytes": 128})
    cache = RedisCache(client, key + ":cache", policy)
    expiring = RedisCache(client, key + ":expiring-cache", policy)
    try:
        await asyncio.gather(*(cache.put(name, Value(name=name), 60) for name in ("a", "b", "c")))
        assert await client.zcard(cache.index) == 2
        hits = [await cache.get(name, Value) for name in ("a", "b", "c")]
        assert sum(v is not None for v in hits) == 2
        isolated = RedisCache(client, key + ":other-cache", policy)
        assert [await isolated.get(name, Value) for name in ("a", "b", "c")] == [None] * 3
        assert await client.get(key) == b"owner-one"  # Cache pruning cannot evict leases.
        assert 0 < await client.ttl(cache.index) <= 60
        entries = await client.zrange(cache.index, 0, -1, withscores=True)

        def forbid_serialization(*args, **kwargs):
            pytest.fail("Invalid TTL must fail before serialization or Redis mutation")

        with monkeypatch.context() as patch:
            patch.setattr(Value, "model_dump", forbid_serialization)
            for ttl in (True, False, 1.5, "60", None):
                with pytest.raises(TypeError, match="Cache TTL must be an integer"):
                    await cache.put("invalid-ttl", Value(name="probe"), ttl)
            for ttl in (0, -1, 61):
                with pytest.raises(ValueError, match="Cache TTL must be between"):
                    await cache.put("invalid-ttl", Value(name="probe"), ttl)
        assert await client.zrange(cache.index, 0, -1, withscores=True) == entries
        assert await client.get(cache.key("invalid-ttl")) is None
        await cache.put("short", Value(name="short"), 1)
        assert await cache.get("short", Value) is None
        assert await client.zrange(cache.index, 0, -1, withscores=True) == entries
        await cache.put("large", Value(name="small"), 60)
        assert await cache.get("large", Value) == Value(name="small")
        await cache.put("large", Value(name="x" * 129), 60)
        assert await cache.get("large", Value) is None
        assert await client.zscore(cache.index, cache.key("large")) is None
        await cache.discard("c")
        assert await cache.get("c", Value) is None
        for payload in (b"broken JSON", b'{"name":["sensitive-cache-sentinel"]}', b"null"):
            await client.set(cache.key("invalid"), payload, ex=60)
            assert await cache.get("invalid", Value) is None
        assert "sensitive-cache-sentinel" not in caplog.text

        for name in ("expired-one", "expired-two"):
            await expiring.put(name, Value(name=name), 1)
        await asyncio.sleep(2.1)  # Both expiry scores are strictly older than Redis's second.
        assert await expiring.get("expired-one", Value) is None
        assert await expiring.get("expired-two", Value) is None
        assert await client.zcard(expiring.index) == 2
        await expiring.put("live", Value(name="live"), 60)
        assert await client.zrange(expiring.index, 0, -1) == [expiring.key("live").encode()]
        assert await expiring.get("live", Value) == Value(name="live")
        assert await client.get(key) == b"owner-one"
        await expiring.discard("live")

        # Seed the exact-second boundary and execute the production script atomically.
        # Retry only if TIME crossed a second between seeding and the script's clock read.
        seed = """
redis.call('DEL', unpack(KEYS))
local boundary_time = tonumber(redis.call('TIME')[1])
redis.call('SET', KEYS[3], ARGV[1], 'PX', 800)
redis.call('ZADD', KEYS[1], boundary_time, KEYS[3], boundary_time - 1, KEYS[4])
"""
        for _ in range(3):
            result = await client.eval(
                seed + STORE + "\nreturn {boundary_time, now}",
                4,
                expiring.index,
                expiring.key("next"),
                expiring.key("boundary"),
                expiring.key("boundary-stale"),
                b'{"name":"boundary"}',
                60,
                policy.max_entries,
                60,
            )
            if result[0] == result[1]:
                assert await client.zrange(expiring.index, 0, -1) == [
                    expiring.key("boundary").encode(),
                    expiring.key("next").encode(),
                ]
                assert await expiring.get("boundary", Value) == Value(name="boundary")
                break
        else:
            pytest.fail("Redis TIME crossed a second in every boundary probe")
    finally:
        await client.delete(
            cache.index,
            *(cache.key(n) for n in ("a", "b", "c", "short", "large", "invalid", "invalid-ttl")),
            expiring.index,
            *(
                expiring.key(n)
                for n in (
                    "expired-one",
                    "expired-two",
                    "live",
                    "next",
                    "boundary",
                    "boundary-stale",
                )
            ),
        )


def deployment_environment(deployment):
    fields = {
        "DB_URL": "db_url",
        "REDIS_URL": "redis_url",
        "CLERK_JWKS_URL": "clerk_jwks_url",
        "CLERK_ISSUER": "clerk_issuer",
        "CLERK_SECRET_KEY": "clerk_secret_key",
        "LEXI_CAMBRIDGE_DB_PATH": "cambridge_path",
        "INFERENCE_API_KEY": "inference_api_key",
        "INFERENCE_BASE_URL": "inference_base_url",
        "LEXI_DECISION_API_KEY": "decision_api_key",
        "LEXI_DECISION_BASE_URL": "decision_base_url",
    }
    env = os.environ.copy()
    for key, field in fields.items():
        value = getattr(deployment, field)
        env[key] = value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)
    env["CONFIG_PATH"] = str(Path(__file__).resolve().parents[4] / "config/config.yaml")
    env["CLERK_AUDIENCE"] = "pycil"
    env["ALLOWED_ORIGINS"] = "https://client.invalid"
    return env


async def test_worker_check_cli_exits_cleanly_without_processing(deployment):
    result = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "pycil.worker", "--check"],
        env=deployment_environment(deployment),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "no generation or user-unit debit" in result.stdout
    assert "test-only" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "change",
    [
        {"DB_URL": "password-sentinel"},
        {"ALLOWED_ORIGINS": "*"},
        {"INFERENCE_BASE_URL": "https://password-sentinel@provider.invalid"},
    ],
)
def test_invalid_deployment_never_echoes_secrets(deployment, monkeypatch, change):
    env = deployment_environment(deployment) | change
    monkeypatch.setattr(os, "environ", env)
    with pytest.raises(ValueError, match="Invalid deployment configuration") as caught:
        Deployment.from_environment()
    assert "password-sentinel" not in str(caught.value)
