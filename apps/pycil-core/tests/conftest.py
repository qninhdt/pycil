"""Shared pytest fixtures for pycil-core tests.

Self-provisioning Postgres (pytest-postgresql) + fakeredis. No external env
required. Suite runs from a clean clone with `pytest`. Per-test isolation
via TRUNCATE on a domain allowlist; the schema is migrated once per session.

Network egress is blocked: Stripe SDK + OpenRouter are mocked at fixture
scope. The `client` fixture wraps the FastAPI app via httpx ASGITransport
with `get_current_user` overridden to a deterministic test user.
"""
from __future__ import annotations

import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import UUID, uuid4

# Required env BEFORE importing pycil_core (config.Settings reads at import).
os.environ.setdefault("AUTH_JWT_SECRET", "test-fake-jwt-secret")
os.environ.setdefault("INTERNAL_API_SECRET", "test-fake-internal")
os.environ.setdefault("OPENROUTER_API_KEY", "test-fake")
os.environ.setdefault("ALLOWED_ORIGINS", "http://test")
# Placeholders so config import succeeds; real values injected in fixtures.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://placeholder/test")
os.environ.setdefault("REDIS_URL", "redis://placeholder/0")

import pytest
import pytest_asyncio


# Make sure the alembic dir is importable.
_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


# ---------------------------------------------------------------------------
# Postgres (pytest-postgresql) — session-scoped DB, schema migrated once.
# ---------------------------------------------------------------------------

from pytest_postgresql import factories as pg_factories  # noqa: E402

# Use a pre-running Postgres process (Docker, CI service container, or local
# postgres). Override via env: PYTEST_PG_HOST / PYTEST_PG_PORT / PYTEST_PG_USER
# / PYTEST_PG_PASSWORD. Defaults match the docker test container.
postgresql_proc = pg_factories.postgresql_noproc(
    host=os.environ.get("PYTEST_PG_HOST", "localhost"),
    port=int(os.environ.get("PYTEST_PG_PORT", "55432")),
    user=os.environ.get("PYTEST_PG_USER", "test"),
    password=os.environ.get("PYTEST_PG_PASSWORD", "test"),
    dbname="postgres",
)


@pytest.fixture(scope="session")
def _pg_dsn(postgresql_proc) -> str:
    """Return a sync psycopg DSN for the test DB on the running Postgres process."""
    pwd = os.environ.get("PYTEST_PG_PASSWORD", "test")
    return (
        f"postgresql+psycopg://{postgresql_proc.user}:{pwd}@"
        f"{postgresql_proc.host}:{postgresql_proc.port}/pycil_test"
    )


@pytest.fixture(scope="session")
def _async_dsn(postgresql_proc) -> str:
    pwd = os.environ.get("PYTEST_PG_PASSWORD", "test")
    return (
        f"postgresql+asyncpg://{postgresql_proc.user}:{pwd}@"
        f"{postgresql_proc.host}:{postgresql_proc.port}/pycil_test"
    )


@pytest.fixture(scope="session")
def _migrate_schema(postgresql_proc, _pg_dsn):
    """Create the test DB and run Alembic upgrade head once per session.

    Not autouse — depended on transitively via `async_engine`. Unit tests
    that don't touch the DB never trigger the Postgres server start.
    """
    import psycopg
    from alembic import command
    from alembic.config import Config

    # Connect to the postgres maintenance DB to CREATE DATABASE.
    pwd = os.environ.get("PYTEST_PG_PASSWORD", "test")
    admin_dsn = (
        f"host={postgresql_proc.host} port={postgresql_proc.port} "
        f"user={postgresql_proc.user} password={pwd} dbname=postgres"
    )
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS pycil_test")
            cur.execute("CREATE DATABASE pycil_test")

    cfg = Config(str(_APP_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_APP_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _pg_dsn)
    os.environ["DATABASE_URL"] = _pg_dsn
    command.upgrade(cfg, "head")
    yield


# ---------------------------------------------------------------------------
# Async engine / session — function-scoped.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_engine(_async_dsn, _migrate_schema):
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(_async_dsn, future=True, pool_pre_ping=False)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(async_engine) -> AsyncGenerator:
    """Per-test AsyncSession. Truncate domain tables BEFORE the test runs."""
    from sqlalchemy import text
    from sqlmodel.ext.asyncio.session import AsyncSession

    # Truncate cycle: order respects FK dependencies via CASCADE.
    truncate_sql = text(
        "TRUNCATE TABLE "
        "test_run_items, test_runs, "
        "user_term_jobs, jobs, user_term_stats, "
        "questions, deck_definitions, definition_paraphrases, "
        "term_example_sentences, definitions, deck_terms, terms, "
        "node_share_links, deck_clones, folder_attributes, nodes, "
        "subscriptions, notifications, users "
        "RESTART IDENTITY CASCADE"
    )
    async with async_engine.begin() as conn:
        await conn.execute(truncate_sql)

    async with AsyncSession(async_engine, expire_on_commit=False) as s:
        yield s


# ---------------------------------------------------------------------------
# Fakeredis — function-scoped client; all redis lookups patched.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def fakeredis_client():
    import fakeredis.aioredis

    r = fakeredis.aioredis.FakeRedis(decode_responses=True)

    # Production uses a shared ConnectionPool; service code calls
    # `await redis.aclose()` per request to return the connection. Fakeredis
    # treats `aclose` as a true close → subsequent ops on the same client
    # blow up. Override to a no-op so a single FakeRedis stays alive across
    # all `get_redis()` call sites in one test.
    async def _noop() -> None:
        return None

    r.aclose = _noop  # type: ignore[method-assign]
    yield r
    await r.flushall()


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch, fakeredis_client):
    """Force every `get_redis()` call site to return the fakeredis client."""
    monkeypatch.setattr(
        "pycil_core.services.redis_pool.get_redis",
        lambda: fakeredis_client,
    )
    # Modules that imported `get_redis` symbol directly.
    for mod in (
        "pycil_core.services.learning_service",
        "pycil_core.services.job_service",
        "pycil_core.services.question_service",
        "pycil_core.services.job_stream_service",
    ):
        try:
            monkeypatch.setattr(f"{mod}._redis", lambda: fakeredis_client)
        except AttributeError:
            pass
    return fakeredis_client


# ---------------------------------------------------------------------------
# Test user factory.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def test_user(session) -> dict:
    from sqlalchemy import text

    email = f"pytest-{uuid4().hex[:8]}@example.test"
    row = (
        await session.execute(
            text(
                "INSERT INTO users (email, name) "
                "VALUES (:e, :n) RETURNING id"
            ),
            {"e": email, "n": "PytestUser"},
        )
    ).one()
    await session.commit()
    return {"id": row.id, "email": email, "name": "PytestUser"}


@pytest_asyncio.fixture
async def second_user(session) -> dict:
    from sqlalchemy import text

    email = f"pytest-2-{uuid4().hex[:8]}@example.test"
    row = (
        await session.execute(
            text(
                "INSERT INTO users (email, name) "
                "VALUES (:e, :n) RETURNING id"
            ),
            {"e": email, "n": "OtherUser"},
        )
    ).one()
    await session.commit()
    return {"id": row.id, "email": email, "name": "OtherUser"}


# ---------------------------------------------------------------------------
# ASGI client — get_current_user overridden, get_session injected.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(async_engine, test_user) -> AsyncGenerator:
    from httpx import ASGITransport, AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession

    from pycil_core.auth import CurrentUser, get_current_user
    from pycil_core.db import get_session
    from pycil_core.main import app

    async def _override_user() -> CurrentUser:
        return CurrentUser(
            id=UUID(str(test_user["id"])),
            email=test_user["email"],
            name=test_user["name"],
        )

    async def _override_session():
        async with AsyncSession(async_engine, expire_on_commit=False) as s:
            try:
                yield s
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_session] = _override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"origin": "http://test"},
        ) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_real_auth(async_engine) -> AsyncGenerator:
    """ASGI client with `get_current_user` NOT overridden — for auth path tests."""
    from httpx import ASGITransport, AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession

    from pycil_core.db import get_session
    from pycil_core.main import app

    async def _override_session():
        async with AsyncSession(async_engine, expire_on_commit=False) as s:
            try:
                yield s
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_session] = _override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"origin": "http://test"},
        ) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
