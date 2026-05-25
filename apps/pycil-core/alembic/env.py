"""Alembic env.py — runs migrations using a SYNC engine (psycopg).

The app uses asyncpg at runtime, but Alembic tooling stays simpler with sync.
Migration URL is derived from DATABASE_URL_ASYNC by stripping the +asyncpg.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _sync_url() -> str:
    raw = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_ASYNC")
    if not raw:
        raise RuntimeError("DATABASE_URL or DATABASE_URL_ASYNC must be set")
    # Convert async URL → sync. asyncpg → psycopg.
    return raw.replace("postgresql+asyncpg://", "postgresql+psycopg://").replace(
        "postgresql://", "postgresql+psycopg://", 1
    )


config.set_main_option("sqlalchemy.url", _sync_url())

# v1 raw-SQL migrations have no SQLAlchemy metadata to autogenerate from.
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
