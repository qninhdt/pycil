"""Shared async test fixtures with disposable PostgreSQL and fake Redis."""

import os
from collections.abc import AsyncGenerator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from pycil.db.models import target_metadata
from pycil.db.session import get_session
from pycil.main import create_app

_POSTGRES_IMAGE = "postgres:16-alpine"


@pytest.fixture(scope="session")
def test_db_url() -> Iterator[str]:
    """Use the CI database when supplied, otherwise provision one with Docker."""
    configured_url = os.environ.get("TEST_DB_URL")
    if configured_url:
        yield configured_url
        return

    with PostgresContainer(_POSTGRES_IMAGE, driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest_asyncio.fixture(autouse=True)
async def fake_redis(monkeypatch):
    """Pre-seed pycil.db.redis with fakeredis so cache/session code needs no server."""
    import fakeredis.aioredis

    from pycil.db import redis as redis_module

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "_redis", fake)
    yield fake
    await fake.flushall()


@pytest_asyncio.fixture
async def engine(test_db_url: str, monkeypatch):
    """A disposable schema, plus the module-level handles bound to it.

    Binding happens here rather than in an autouse fixture so that a pure test —
    FSRS arithmetic, config validation, a schema shape — never provisions Postgres
    at all. An autouse fixture would start a container for every test in the suite,
    including the ones that provably touch no database, which is the difference
    between a unit suite that runs in a second and one that cannot run without
    Docker.
    """
    eng = create_async_engine(test_db_url, poolclass=None)
    async with eng.begin() as conn:
        await conn.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
        await conn.exec_driver_sql("CREATE SCHEMA public")
        await conn.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
        await conn.run_sync(target_metadata.create_all)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("pycil.db.session.engine", eng)
    monkeypatch.setattr("pycil.db.session.async_session_factory", factory)
    yield eng
    async with eng.begin() as conn:
        await conn.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
        await conn.exec_driver_sql("CREATE SCHEMA public")
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def app(engine):
    """The application under test, with its session bound to the test database."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as s:
            yield s

    application = create_app()
    application.dependency_overrides[get_session] = _override
    return application



@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# The Clerk test issuer/JWKS lives in `tests/support/` because Phase 12 owns the
# test-support tree; registering it here makes its fixtures available to every
# test module without each one importing the module directly.
pytest_plugins = ["tests.support.clerk_jwks"]
