"""Application DDL; native checkpoint tables retain their own setup history."""

import asyncio

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from pycil.infrastructure.database import Base, register_models

register_models()
config = context.config


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table":
        return obj.schema in (None, "public") and name not in {
            "alembic_version",
            "checkpoints",
            "checkpoint_blobs",
            "checkpoint_writes",
            "checkpoint_migrations",
        }
    return True


def migrate(connection):
    connection.execute(text("SET LOCAL search_path TO public"))
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        include_schemas=True,
        include_object=include_object,
        compare_type=True,
        version_table="alembic_version",
        version_table_schema="public",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run():
    url = config.get_main_option("sqlalchemy.url")
    if not url or not url.startswith("postgresql+asyncpg://"):
        raise ValueError("Explicit PostgreSQL application database URL required")
    engine = create_async_engine(
        url,
        poolclass=pool.NullPool,
        hide_parameters=True,
        connect_args={
            "timeout": 5,
            "server_settings": {
                "search_path": "public",
                "lock_timeout": "5s",
                "statement_timeout": "120s",
            },
        },
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(migrate)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Use the explicit online migration gate")
elif "connection" in config.attributes:
    migrate(config.attributes["connection"])
else:
    asyncio.run(run())
