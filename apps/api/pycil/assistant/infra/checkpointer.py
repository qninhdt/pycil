"""Lifespan-managed, migration-owned LangGraph Postgres checkpointer."""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from pycil.config import settings


async def open_checkpointer() -> tuple[AsyncConnectionPool, AsyncPostgresSaver]:
    """Open a dedicated psycopg pool only when the assistant is configured.

    Alembic creates the checkpoint schema. Calling ``setup`` here would let
    runtime credentials mutate production schema, so this only validates it.
    """
    pool = AsyncConnectionPool(
        conninfo=settings.assistant_psycopg_url,
        min_size=1,
        max_size=5,
        open=False,
        kwargs={"autocommit": True},
    )
    await pool.open(wait=True)
    async with pool.connection() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT max(v) FROM checkpoint_migrations")
            row = await cursor.fetchone()
    if row is None or row[0] != 9:
        await pool.close()
        raise RuntimeError("assistant_checkpoint_schema_outdated")
    return pool, AsyncPostgresSaver(pool)
