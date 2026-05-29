"""Alembic env.py — runs migrations using a SYNC engine (psycopg).

The app uses asyncpg at runtime, but Alembic tooling stays simpler with sync.
Migration URL is derived from DATABASE_URL_ASYNC by stripping the +asyncpg.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

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

# SQLModel table models register on SQLModel.metadata at import. Pointing
# Alembic here enables `--autogenerate` to diff models against the live schema.
# Existing raw-SQL migrations remain the source of truth for `upgrade`.
import shared.db  # noqa: E402,F401  (import side effect: registers all table models)
from sqlmodel import SQLModel  # noqa: E402

target_metadata = SQLModel.metadata


def _include_object(obj, name, type_, reflected, compare_to):
    """Limit autogenerate to column parity on modeled tables.

    Models are intentionally column-only mappings for the ORM; indexes, foreign
    keys, unique constraints, and check constraints are owned by the raw-SQL
    migrations and are NOT declared on the models. Excluding those object types
    keeps the parity gate focused on what the models actually assert: table +
    column existence, type, and nullability.
    """
    if type_ == "table":
        return name in target_metadata.tables
    if type_ in ("index", "foreign_key_constraint", "unique_constraint"):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _widen_alembic_version(connection) -> None:
    """Widen alembic_version.version_num to fit revision IDs > 32 chars.

    Default Alembic creates VARCHAR(32); descriptive IDs like
    `0013_user_definition_stats_and_overrides` (41 chars) overflow it.
    Idempotent: ALTER TYPE TEXT is a no-op when already TEXT.
    """
    from sqlalchemy import text as _t
    connection.execute(
        _t(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(64) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
    )
    connection.execute(
        _t("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")
    )


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _widen_alembic_version(connection)
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
