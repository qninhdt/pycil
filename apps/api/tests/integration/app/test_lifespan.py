import pytest
from httpx import ASGITransport, AsyncClient

from pycil.app import resources
from pycil.app.config import load_config
from pycil.app.factory import create_app
from pycil.app.settings import ApiSettings
from pycil.observability.http import ObservedAsyncClient
from pycil.vocabulary.references.importer import import_reference
from tests.support.reference import reference_file, reference_word


@pytest.mark.xdist_group("serial_redis")
@pytest.mark.parametrize("failed_component", ["database", "redis", "redis_timeout"])
async def test_readiness_dependency_failures_return_safe_503_and_preserve_health(
    database, redis_store, redis_container, failed_component
):
    import contextlib
    from time import perf_counter
    from types import SimpleNamespace

    from redis.asyncio import Redis
    from sqlalchemy.engine import make_url

    from pycil.infrastructure.database import connect
    from pycil.vocabulary.search import SearchIndex

    redis, _ = redis_store
    app = create_app()
    app.state.config = load_config()
    app.state.deployment = SimpleNamespace(allowed_origins=[])
    index = SearchIndex(
        database.sessions,
        policy=load_config().vocabulary.search_runtime,
        query_policy=load_config().vocabulary.search,
    )
    broken_engine = broken_redis = timeout_redis = timeout_container = None
    try:
        await index.start()
        app.state.search = index
        app.state.engine, app.state.redis = database.engine, redis
        if failed_component == "database":
            url = make_url(database.url).set(
                username="unavailable_test_identity", password="private-readiness-marker"
            )
            broken_engine, _ = connect(url.render_as_string(hide_password=False))
            app.state.engine = broken_engine
        elif failed_component == "redis":
            broken_redis = Redis(
                host=redis_container.get_container_host_ip(),
                port=int(redis_container.get_exposed_port(6379)),
                username="unavailable_test_identity",
                password="private-readiness-marker",
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            app.state.redis = broken_redis
        elif failed_component == "redis_timeout":
            from testcontainers.community.redis import RedisContainer

            timeout_container = RedisContainer("redis:8.10.2-alpine3.23")
            timeout_container.start()
            timeout_redis = Redis(
                host=timeout_container.get_container_host_ip(),
                port=int(timeout_container.get_exposed_port(6379)),
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            app.state.redis = timeout_redis
            await timeout_redis.execute_command("CLIENT", "PAUSE", 1500, "ALL")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://api.test"
        ) as client:
            started = perf_counter()
            response = await client.get("/readyz")
            if failed_component == "redis_timeout":
                assert perf_counter() - started < 1
            assert response.status_code == 503 and response.json()["code"] == "not_ready"
            assert "private-readiness-marker" not in response.text
            assert (await client.get("/livez")).json() == {"status": "ok"}
        assert database.engine.pool.checkedout() == 0
    finally:
        await index.close()
        if timeout_redis is not None:
            with contextlib.suppress(Exception):
                await timeout_redis.execute_command("CLIENT", "UNPAUSE")
            await timeout_redis.aclose()
        if timeout_container is not None:
            timeout_container.stop()
        if broken_redis is not None:
            await broken_redis.aclose()
        if broken_engine is not None:
            await broken_engine.dispose()


async def test_real_lifespan_checks_search_readiness_and_cleans_owned_resources(
    database, redis_container, monkeypatch, tmp_path
):
    await import_reference(
        database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
    )
    address = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    variables = {
        "DB_URL": database.url,
        "REDIS_URL": f"redis://{address}:{port}/0",
        "CLERK_JWKS_URL": "https://identity.invalid/jwks",
        "CLERK_ISSUER": "https://identity.invalid",
        "CLERK_SECRET_KEY": "test-only",
        "LLM_API_KEY": "test-only",
        "LLM_BASE_URL": "https://provider.invalid/v1",
        "DECISION_API_KEY": "test-only",
        "DECISION_BASE_URL": "https://decision.invalid",
        "CLERK_AUDIENCE": "",
        "ALLOWED_ORIGINS": "http://web.example.test",
    }
    for key, value in variables.items():
        monkeypatch.setenv(key, value)

    def forbidden_generation_client(*args, **kwargs):
        pytest.fail("API must not initialize the worker generation client")

    monkeypatch.setattr(resources, "StructuredLLM", forbidden_generation_client)
    app = create_app()
    async with app.router.lifespan_context(app):
        search, client = app.state.search, app.state.http
        assert not hasattr(app.state, "structured_llm")
        assert isinstance(client, ObservedAsyncClient)
        for name in ("word", "sense", "artifact", "user_id"):
            assert getattr(app.state, f"{name}_store").attributes == {
                "store": name,
                "backend": "memory",
            }
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://api.example.test"
        ) as http:
            assert (await http.get("/readyz")).status_code == 200
            response = await http.get(
                "/v1/words:search", params={"query": "bank", "include_reference": "true"}
            )
            assert response.status_code == 200
            assert response.json()["items"][0]["kind"] == "reference"
            search.snapshot = None
            response = await http.get("/readyz", headers={"Origin": "http://web.example.test"})
            assert response.status_code == 503
            assert response.json()["error"] == "not_ready"
            assert response.headers["access-control-allow-origin"] == "http://web.example.test"
            assert (await http.get("/livez")).json() == {"status": "ok"}
            for removed_path in ("/health", "/ready", "/health/live", "/health/ready"):
                assert (await http.get(removed_path)).status_code == 404
            schema = (await http.get("/openapi.json")).json()
            assert "/livez" not in schema["paths"]
            assert "/readyz" not in schema["paths"]
    assert client.is_closed
    assert search.snapshot is None
    assert not hasattr(app.state, "engine")


async def test_schema_startup_failure_disposes_the_acquired_engine(database, monkeypatch):
    acquired = []
    connect = resources.observed_connect

    def captured_connection(url, **policy):
        engine, sessions = connect(url, **policy)
        acquired.append((engine, engine.pool))
        return engine, sessions

    monkeypatch.setattr(resources, "observed_connect", captured_connection)
    deployment = deployment_for(database.url, "redis://127.0.0.1:1/0")
    with pytest.raises(RuntimeError, match="Runtime initialization failed"):
        async with resources.api_resources(load_config(), deployment):
            pytest.fail("An empty reference must prevent startup")
    assert len(acquired) == 1
    engine, previous_pool = acquired[0]
    assert engine.pool is not previous_pool
    assert previous_pool.checkedout() == 0


def deployment_for(db_url, redis_url):
    return ApiSettings(
        db_url=db_url,
        redis_url=redis_url,
        clerk_jwks_url="https://identity.invalid/jwks",
        clerk_issuer="https://identity.invalid",
        clerk_audience=None,
        clerk_secret_key="test-only",
        llm_api_key="test-only",
        llm_base_url="https://provider.invalid/v1",
        decision_api_key="test-only",
        decision_base_url="https://decision.invalid",
        allowed_origins=[],
    )


@pytest.mark.parametrize("cleanup_failure", ["error", "timeout"])
async def test_failed_redis_closer_does_not_prevent_engine_cleanup(
    database, redis_store, monkeypatch, cleanup_failure
):
    import asyncio

    redis, _ = redis_store
    acquired, closed = [], []
    connect, close_redis = resources.observed_connect, redis.aclose

    def captured_connection(url, **policy):
        engine, sessions = connect(url, **policy)
        acquired.append((engine, engine.pool))
        return engine, sessions

    async def failed_closer():
        await close_redis()
        closed.append(True)
        if cleanup_failure == "timeout":
            await asyncio.Event().wait()
        raise RuntimeError("private cleanup detail")

    await redis.ping()
    monkeypatch.setattr(resources, "observed_connect", captured_connection)
    monkeypatch.setattr(resources.Redis, "from_url", lambda *args, **kwargs: redis)
    monkeypatch.setattr(redis, "aclose", failed_closer)
    config = load_config()
    config = config.model_copy(
        update={
            "system": config.system.model_copy(
                update={
                    "lifecycle": config.system.lifecycle.model_copy(
                        update={"cleanup_timeout_seconds": 0.1}
                    )
                }
            )
        }
    )
    try:
        with pytest.raises(RuntimeError, match="^Runtime resource cleanup failed$"):
            async with asyncio.timeout(2):
                async with resources.api_resources(
                    config, deployment_for(database.url, "redis://127.0.0.1:1/0")
                ):
                    pytest.fail("empty reference dataset must prevent startup")
        assert closed == [True]
        engine, previous_pool = acquired[0]
        assert engine.pool is not previous_pool and previous_pool.checkedout() == 0
    finally:
        monkeypatch.setattr(redis, "aclose", close_redis)


async def test_startup_cancellation_closes_acquired_resources_before_return(
    database, redis_store, monkeypatch, tmp_path
):
    import asyncio

    await import_reference(
        database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
    )
    redis, _ = redis_store
    connect, verify, close_redis = resources.observed_connect, resources.verify_schema, redis.aclose
    acquired, closed, verified = [], [], asyncio.Event()

    def captured_connection(url, **policy):
        engine, sessions = connect(url, **policy)
        acquired.append((engine, engine.pool))
        return engine, sessions

    async def paused_schema_gate(engine):
        await verify(engine)
        verified.set()
        await asyncio.Event().wait()

    async def captured_closer():
        await close_redis()
        closed.append(True)

    async def initialize():
        async with resources.api_resources(
            load_config(), deployment_for(database.url, "redis://127.0.0.1:1/0")
        ):
            pytest.fail("cancelled initialization must never publish resources")

    monkeypatch.setattr(resources, "observed_connect", captured_connection)
    monkeypatch.setattr(resources, "verify_schema", paused_schema_gate)
    monkeypatch.setattr(resources.Redis, "from_url", lambda *args, **kwargs: redis)
    monkeypatch.setattr(redis, "aclose", captured_closer)
    task = asyncio.create_task(initialize())
    try:
        async with asyncio.timeout(5):
            await verified.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert closed == [True]
        engine, previous_pool = acquired[0]
        assert engine.pool is not previous_pool and previous_pool.checkedout() == 0
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        monkeypatch.setattr(redis, "aclose", close_redis)


async def test_api_specific_startup_failure_redacts_details_and_closes_shared_resources(
    database,
    redis_container,
    monkeypatch,
    tmp_path,
):
    await import_reference(
        database.sessions,
        reference_file(tmp_path / "reference.jsonl", [reference_word()]),
    )
    acquired = []
    connect = resources.observed_connect

    def captured_connection(url, **policy):
        engine, sessions = connect(url, **policy)
        acquired.append((engine, engine.pool))
        return engine, sessions

    async def failed_search(self):
        raise RuntimeError("private-search-startup-detail")

    monkeypatch.setattr(resources, "observed_connect", captured_connection)
    monkeypatch.setattr(resources.SearchIndex, "start", failed_search)
    deployment = deployment_for(
        database.url,
        f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}/0",
    )
    from structlog.testing import capture_logs

    with capture_logs() as logs:
        with pytest.raises(
            RuntimeError, match="^Runtime initialization failed; verify API dependencies$"
        ):
            async with resources.api_resources(load_config(), deployment):
                pytest.fail("failed index must prevent API startup")
    events = [record["event"] for record in logs]
    assert "resources_initialized" not in events
    assert events.count("resources_initialization_failed") == 1
    assert events.count("resources_closed") == 1
    engine, previous_pool = acquired[0]
    assert engine.pool is not previous_pool and previous_pool.checkedout() == 0
