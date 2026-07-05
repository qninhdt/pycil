"""Shared test fixtures: async DB session + app with overridden deps.

Uses TEST_DB_URL (a disposable Postgres) if set, else the configured db_url.
Creates all pycil tables from SQLModel metadata per session.
"""

import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pycil.db.models import target_metadata
from pycil.db.session import get_session
from pycil.main import create_app

TEST_DB_URL = os.environ.get(
    "TEST_DB_URL", "postgresql+asyncpg://pycil:test@127.0.0.1:55432/pycil"
)


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
async def engine():
    eng = create_async_engine(TEST_DB_URL, poolclass=None)
    async with eng.begin() as conn:
        await conn.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
        await conn.run_sync(target_metadata.drop_all)
        await conn.run_sync(target_metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(target_metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def client(engine) -> AsyncGenerator[AsyncClient, None]:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as s:
            yield s

    app = create_app()
    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
