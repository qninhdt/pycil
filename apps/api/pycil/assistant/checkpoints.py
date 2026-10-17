from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import partial

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.engine import make_url

from pycil.observability.database import ObservedPsycopgCursor, ObservedPsycopgPool


def checkpoint_dsn(url: str) -> str:
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg":
        raise ValueError("Checkpoint storage requires the application PostgreSQL URL")
    return str(parsed.set(drivername="postgresql").render_as_string(hide_password=False))


@asynccontextmanager
async def checkpoint_pool(
    url: str,
    *,
    name: str = "checkpoint",
    min_size: int = 1,
    max_size: int = 3,
    timeout_seconds: float = 30,
    startup_timeout_seconds: float = 30,
) -> AsyncGenerator[AsyncConnectionPool[AsyncConnection[DictRow]]]:
    async with ObservedPsycopgPool(
        checkpoint_dsn(url),
        name=name,
        min_size=min_size,
        max_size=max_size,
        timeout=timeout_seconds,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
            "cursor_factory": partial(ObservedPsycopgCursor, observation_name=name),
            "options": "-c search_path=public",
        },
    ) as pool:
        await pool.wait(timeout=startup_timeout_seconds)
        yield pool


@asynccontextmanager
async def checkpoint_connection(
    url: str,
) -> AsyncGenerator[AsyncConnection[DictRow]]:
    connection = await AsyncConnection[DictRow].connect(
        checkpoint_dsn(url),
        autocommit=True,
        connect_timeout=5,
        prepare_threshold=0,
        row_factory=dict_row,
        options="-c search_path=public",
    )
    async with connection:
        yield connection


async def setup_checkpoints(url: str) -> None:
    # Native setup uses autocommit (including CREATE INDEX CONCURRENTLY).
    # No DDL or local substitute checkpoint tables appear in Pycil's Alembic history.
    async with checkpoint_connection(url) as connection:
        await connection.execute("SET lock_timeout = '5s'")
        await connection.execute("SET statement_timeout = '120s'")
        await AsyncPostgresSaver(connection).setup()
