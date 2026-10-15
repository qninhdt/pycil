from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.engine import make_url

from pycil.infrastructure.observability import observe_pool_acquisition


class CheckpointPool(AsyncConnectionPool[AsyncConnection[DictRow]]):
    async def getconn(self, timeout: float | None = None) -> AsyncConnection[DictRow]:
        with observe_pool_acquisition("checkpoint"):
            return await super().getconn(timeout=timeout)


def checkpoint_dsn(url: str) -> str:
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg":
        raise ValueError("Checkpoint storage requires the application PostgreSQL URL")
    return str(parsed.set(drivername="postgresql").render_as_string(hide_password=False))


@asynccontextmanager
async def checkpoint_pool(
    url: str,
    *,
    min_size: int = 1,
    max_size: int = 3,
    timeout_seconds: float = 30,
    startup_timeout_seconds: float = 30,
) -> AsyncGenerator[AsyncConnectionPool[AsyncConnection[DictRow]]]:
    async with CheckpointPool(
        checkpoint_dsn(url),
        min_size=min_size,
        max_size=max_size,
        timeout=timeout_seconds,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
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
