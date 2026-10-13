"""Session-owned infrastructure and per-test PostgreSQL/Redis isolation."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from redis.asyncio import Redis
from sqlalchemy.engine import make_url
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from pycil.app.migrate import migrate
from pycil.infrastructure.database import connect


@pytest.fixture(scope="session")
def postgres():
    container = PostgresContainer("postgres:18.6", driver="psycopg")
    try:
        container.start()
        yield container
    finally:
        container.stop()


@pytest.fixture
async def database(postgres):
    name = "test_" + uuid4().hex
    address = make_url(postgres.get_connection_url())
    admin_url = address.set(drivername="postgresql").render_as_string(hide_password=False)
    connection = await psycopg.AsyncConnection.connect(admin_url, autocommit=True)
    async with connection:
        await connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    engine = None
    try:
        url = address.set(drivername="postgresql+asyncpg", database=name).render_as_string(
            hide_password=False
        )
        await asyncio.to_thread(migrate, url)
        engine, sessions = connect(url)
        yield SimpleNamespace(url=url, engine=engine, sessions=sessions)
    finally:
        if engine is not None:
            await engine.dispose()
        connection = await psycopg.AsyncConnection.connect(admin_url, autocommit=True)
        async with connection:
            await connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.fixture(scope="session")
def redis_container():
    container = RedisContainer("redis:8.10.2-alpine3.23")
    try:
        container.start()
        yield container
    finally:
        container.stop()


@pytest.fixture
async def redis_store(redis_container):
    client = Redis(
        host=redis_container.get_container_host_ip(),
        port=int(redis_container.get_exposed_port(6379)),
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    namespace = "test:" + uuid4().hex
    try:
        yield client, namespace
    finally:
        keys = [key async for key in client.scan_iter(match=namespace + "*")]
        if keys:
            await client.delete(*keys)
        await client.aclose()
