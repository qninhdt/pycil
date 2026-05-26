"""Worker test fixtures.

Mirrors `apps/pycil-core/tests/conftest.py` for the worker package: shared
Postgres (pytest-postgresql), fakeredis, and a fake `arq.ctx` for direct
job invocation. Worker tests run with **zero** outbound network calls —
`worker.llm.openrouter.generate_with_schema` is monkeypatched per-test.
"""
from __future__ import annotations

import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

# Required env BEFORE any worker import.
os.environ.setdefault("OPENROUTER_API_KEY", "test-fake")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://placeholder/test")
os.environ.setdefault("REDIS_URL", "redis://placeholder/0")

import pytest
import pytest_asyncio


_APP_ROOT = Path(__file__).resolve().parents[1]
_CORE_ROOT = _APP_ROOT.parent / "pycil-core"
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


# ---------------------------------------------------------------------------
# Postgres + Alembic — share schema with pycil-core (same Alembic head).
# ---------------------------------------------------------------------------

from pytest_postgresql import factories as pg_factories  # noqa: E402

postgresql_proc = pg_factories.postgresql_noproc(
    host=os.environ.get("PYTEST_PG_HOST", "localhost"),
    port=int(os.environ.get("PYTEST_PG_PORT", "55432")),
    user=os.environ.get("PYTEST_PG_USER", "test"),
    password=os.environ.get("PYTEST_PG_PASSWORD", "test"),
    dbname="postgres",
)


@pytest.fixture(scope="session")
def _pg_dsn(postgresql_proc) -> str:
    pwd = os.environ.get("PYTEST_PG_PASSWORD", "test")
    return (
        f"postgresql+psycopg://{postgresql_proc.user}:{pwd}@"
        f"{postgresql_proc.host}:{postgresql_proc.port}/pycil_worker_test"
    )


@pytest.fixture(scope="session")
def _async_dsn(postgresql_proc) -> str:
    pwd = os.environ.get("PYTEST_PG_PASSWORD", "test")
    return (
        f"postgresql+asyncpg://{postgresql_proc.user}:{pwd}@"
        f"{postgresql_proc.host}:{postgresql_proc.port}/pycil_worker_test"
    )


@pytest.fixture(scope="session")
def _migrate_schema(postgresql_proc, _pg_dsn):
    """Create test DB + apply pycil-core's Alembic migrations.

    Not autouse — opt-in via `async_engine` so unit tests skip Postgres start.
    """
    import psycopg
    from alembic import command
    from alembic.config import Config

    pwd = os.environ.get("PYTEST_PG_PASSWORD", "test")
    admin_dsn = (
        f"host={postgresql_proc.host} port={postgresql_proc.port} "
        f"user={postgresql_proc.user} password={pwd} dbname=postgres"
    )
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS pycil_worker_test")
            cur.execute("CREATE DATABASE pycil_worker_test")

    cfg = Config(str(_CORE_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_CORE_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _pg_dsn)
    os.environ["DATABASE_URL"] = _pg_dsn
    command.upgrade(cfg, "head")
    yield


@pytest_asyncio.fixture
async def async_engine(_async_dsn, _migrate_schema):
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(_async_dsn, future=True, pool_pre_ping=False)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def fakeredis_client():
    import fakeredis.aioredis

    r = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def _noop() -> None:
        return None

    r.aclose = _noop  # type: ignore[method-assign]
    yield r
    await r.flushall()


@pytest.fixture
def arq_ctx(fakeredis_client) -> dict:
    """Minimal arq context — `redis` + the retry counters the jobs read."""
    return {"redis": fakeredis_client, "job_try": 1, "max_tries": 1}


@pytest.fixture
def _bind_worker_session(monkeypatch, async_engine):
    """Make `worker.db.SessionLocal` bind to the test engine.

    Worker job modules import `SessionLocal` by name at module load
    (`from worker.db import SessionLocal`), so we have to patch each
    importer's symbol — patching `worker.db.SessionLocal` alone does
    nothing since the binding is already resolved.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    factory = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr("worker.db.SessionLocal", factory)
    for mod in (
        "worker.jobs.generate_term",
        "worker.jobs.generate_question",
        "worker.jobs.translate_definition",
        "worker.jobs.tts_render",
        "worker.jobs.lifecycle",
    ):
        try:
            monkeypatch.setattr(f"{mod}.SessionLocal", factory)
        except (AttributeError, ImportError):
            pass
    return factory


@pytest_asyncio.fixture
async def session(async_engine, _bind_worker_session) -> AsyncGenerator:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    truncate_sql = text(
        "TRUNCATE TABLE "
        "user_term_jobs, jobs, user_term_stats, "
        "questions, deck_definitions, definition_paraphrases, "
        "term_example_sentences, definitions, deck_terms, terms, "
        "nodes, users "
        "RESTART IDENTITY CASCADE"
    )
    async with async_engine.begin() as conn:
        await conn.execute(truncate_sql)

    async with AsyncSession(async_engine, expire_on_commit=False) as s:
        yield s
