"""Native checkpoint persistence; schema setup belongs only to the migration gate."""

from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.engine import make_url

CHECKPOINT_SCHEMA = "checkpoints"


def checkpoint_dsn(url: str):
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg":
        raise ValueError("Checkpoint storage requires the application PostgreSQL URL")
    return parsed.set(drivername="postgresql").render_as_string(hide_password=False)


@asynccontextmanager
async def checkpoint_pool(url: str):
    async with AsyncConnectionPool(
        checkpoint_dsn(url),
        min_size=1,
        max_size=5,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
            "options": f"-c search_path={CHECKPOINT_SCHEMA}",
        },
    ) as pool:
        await pool.wait()
        yield pool


@asynccontextmanager
async def checkpoint_connection(url: str):
    connection = await AsyncConnection.connect(
        checkpoint_dsn(url),
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
        options=f"-c search_path={CHECKPOINT_SCHEMA}",
    )
    async with connection:
        yield connection


async def setup_checkpoints(url: str):
    # Native setup uses autocommit (including CREATE INDEX CONCURRENTLY).
    # No DDL or local substitute checkpoint tables appear in Pycil's Alembic history.
    async with checkpoint_connection(url) as connection:
        await connection.execute(f"CREATE SCHEMA IF NOT EXISTS {CHECKPOINT_SCHEMA}")
        await AsyncPostgresSaver(connection).setup()
