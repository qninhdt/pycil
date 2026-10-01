"""Lifespan-managed LangGraph Postgres checkpointer."""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from pycil.platform.settings import settings


async def open_checkpointer() -> tuple[AsyncConnectionPool, AsyncPostgresSaver]:
    """Open the dedicated pool and let LangGraph apply its own checkpoint schema."""
    pool = AsyncConnectionPool(
        conninfo=settings.assistant_psycopg_url,
        min_size=1,
        max_size=5,
        open=False,
        kwargs={"autocommit": True},
    )
    await pool.open(wait=True)
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()
    return pool, checkpointer
