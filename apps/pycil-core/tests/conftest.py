"""Shared pytest fixtures for pycil-core tests.

Skips the suite when DATABASE_URL_TEST is unset so CI can opt in only
when an isolated DB is available.
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


REQUIRES_DB = pytest.mark.skipif(
    not os.getenv("DATABASE_URL_TEST"),
    reason="DATABASE_URL_TEST not set",
)


@pytest_asyncio.fixture
async def engine():
    db_url = os.environ["DATABASE_URL_TEST"]
    eng = create_async_engine(db_url, future=True)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


@pytest_asyncio.fixture
async def test_user(session: AsyncSession) -> dict:
    """Insert a fresh user; cleanup deferred to test-DB truncate between runs."""
    email = f"pytest-{uuid4().hex[:8]}@example.test"
    row = (
        await session.execute(
            text(
                "INSERT INTO users (email, name) VALUES (:e, :n) RETURNING id"
            ),
            {"e": email, "n": "PytestUser"},
        )
    ).one()
    await session.commit()
    return {"id": row.id, "email": email, "name": "PytestUser"}


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    from pycil_core.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
