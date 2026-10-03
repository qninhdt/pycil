"""New isolated PostgreSQL databases; never infer a development database target."""

import asyncio
import os
import sqlite3
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from pycil.account.models import User
from pycil.config import Deployment, load_config
from pycil.database import connect
from pycil.migrate import migrate


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
async def database():
    target = os.environ.get("PYCIL_TEST_DB_URL")
    if not target:
        pytest.fail("Integration tests require explicit disposable PYCIL_TEST_DB_URL")
    admin_url = make_url(target)
    if admin_url.database != "rewrite_test":
        pytest.fail("Use the dedicated rewrite_test container database, not application data")
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    name = "pycil_test_" + uuid4().hex
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = admin_url.set(database=name).render_as_string(hide_password=False)
    engine = None
    try:
        await asyncio.to_thread(migrate, url)
        engine, sessions = connect(url)
        yield engine, sessions, url
    finally:
        if engine:
            await engine.dispose()
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE "{name}"'))
        await admin.dispose()


@pytest.fixture
async def user(database):
    _, sessions, _ = database
    async with sessions() as session, session.begin():
        user = User(
            clerk_subject="user_" + uuid4().hex,
            settings={},
            cycle_anchor=datetime(2026, 1, 31, 12, tzinfo=UTC),
        )
        session.add(user)
        await session.flush()
    return user


@pytest.fixture
def redis_url():
    url = os.environ.get("PYCIL_TEST_REDIS_URL")
    if not url:
        pytest.fail("Bootstrap tests require explicit disposable PYCIL_TEST_REDIS_URL")
    parsed = urlsplit(url)
    if parsed.scheme != "redis" or parsed.hostname != "127.0.0.1" or parsed.path != "/15":
        pytest.fail("Use localhost DB 15 on the dedicated rewrite test Redis container")
    return url


@pytest.fixture
async def redis_namespace(redis_url):
    client = Redis.from_url(redis_url)
    key = "pycil:rewrite:test:" + uuid4().hex
    try:
        yield client, key
    finally:
        # Only this fixture's exact key. No shared flush/scan-and-delete.
        await client.delete(key)
        await client.aclose()


@pytest.fixture
async def senses(database):
    engine, _, _ = database
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO lexi.words(id,lemma,match_key,entry_type,generation_state) "
                "VALUES(1,'bank','bank','WORD','DONE')"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO lexi.senses(id,word_id,pos,tier) "
                "VALUES(1,1,'NOUN','CORE'),(2,1,'NOUN','COMMON')"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO lexi.definitions(sense_id,content) "
                "VALUES(1,'a financial institution'),(2,'the side of a river')"
            )
        )
    return [1, 2]


@pytest.fixture
def reference(tmp_path):
    # Empty native Cambridge schema is enough for lifecycle/read-only search tests.
    # This is an external SQLite reference, NOT a fake Lexi service or DTO.
    path = tmp_path / "reference.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE words(id INTEGER PRIMARY KEY, word TEXT, display_form TEXT, "
            "entry_type TEXT, status TEXT);"
            "CREATE TABLE entries(id INTEGER PRIMARY KEY, word_id INTEGER, pos TEXT, "
            "definition TEXT, examples TEXT, cefr_level TEXT, entry_order INTEGER, "
            "pronunciation_uk TEXT, pronunciation_us TEXT, phrase_title TEXT);"
            "CREATE TABLE senses(id INTEGER PRIMARY KEY, entry_id INTEGER, definition TEXT, "
            "cefr_level TEXT, phrase_title TEXT, sense_order INTEGER);"
            "CREATE TABLE examples(id INTEGER PRIMARY KEY, sense_id INTEGER, "
            "example TEXT, example_order INTEGER);"
            "CREATE TABLE word_alternatives(word_id INTEGER, alternative_word TEXT, "
            "alternative_type TEXT);"
        )
    return path


@pytest.fixture
def deployment(database, redis_url, reference):
    _, _, url = database
    return Deployment(
        db_url=SecretStr(url),
        redis_url=SecretStr(redis_url),
        clerk_jwks_url="https://identity.invalid/jwks",
        clerk_issuer="https://identity.invalid",
        clerk_audience="pycil",
        clerk_secret_key=SecretStr("test-only-clerk-secret"),
        allowed_origins=["https://client.invalid"],
        cambridge_path=reference,
        inference_api_key=SecretStr("test-only-inference-key"),
        inference_base_url="https://inference.invalid/v1",
        decision_api_key=SecretStr("test-only-decision-key"),
        decision_base_url="https://decision.invalid",
    )


@pytest.fixture
def no_inference(monkeypatch):
    from lexi_ai.inference.decision import DecisionModel
    from lexi_ai.inference.llm import OpenAIStructuredLLM

    async def forbidden(*args, **kwargs):
        pytest.fail("Bootstrap tests must never invoke a paid provider")

    # Native Lexi reads/storage remain real; reject only the inference boundary.
    monkeypatch.setattr(OpenAIStructuredLLM, "complete", forbidden)
    monkeypatch.setattr(DecisionModel, "decide", forbidden)
