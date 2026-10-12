"""Application metadata and per-operation sessions; Lexi owns its own DDL."""

from enum import StrEnum

from lexi_ai import metadata as lexi_metadata
from sqlalchemy import Enum, MetaData, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


lexi_metadata.tables["lexi.senses"].to_metadata(Base.metadata)


def enum_column(enum: type[StrEnum]):
    return Enum(
        enum,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        name=enum.__name__.lower(),
    )


def connect(url: str):
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("Pycil requires an explicit PostgreSQL async URL")
    engine = create_async_engine(
        url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"server_settings": {"search_path": "public"}},
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def transaction_lock(session, key: str):
    """Serialize one business resource; release automatically with its transaction."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
    )


def register_models():
    # Import registration is explicit, with no client/engine construction.
    from pycil.account import models as account
    from pycil.assistant import models as assistant
    from pycil.library import models as library
    from pycil.study import models as study

    return account, library, study, assistant


async def verify_schema(engine):
    """Read-only startup/readiness check; never repair or migrate implicitly."""
    from alembic.script import ScriptDirectory
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from lexi_ai.migrations import inspect_head

    from pycil.migrate import migration_config

    application_head = ScriptDirectory.from_config(
        migration_config("postgresql+asyncpg://")
    ).get_current_head()
    async with engine.connect() as connection:
        app = (
            (await connection.execute(text("SELECT version_num FROM public.alembic_version")))
            .scalars()
            .all()
        )
        lexi = (
            (await connection.execute(text("SELECT version_num FROM lexi.alembic_version")))
            .scalars()
            .all()
        )
        checkpoints = (
            (
                await connection.execute(
                    text("SELECT v FROM checkpoints.checkpoint_migrations ORDER BY v")
                )
            )
            .scalars()
            .all()
        )
        if app != [application_head] or lexi != [inspect_head()]:
            raise RuntimeError("schema_version_mismatch; run the explicit migration gate")
        if checkpoints != list(range(len(AsyncPostgresSaver.MIGRATIONS))):
            raise RuntimeError("checkpoint_version_mismatch; run the explicit migration gate")
        # Version rows alone do not prove the owned/external tables still exist.
        register_models()
        required = {
            f"{table.schema or 'public'}.{table.name}" for table in Base.metadata.tables.values()
        }
        required |= {
            f"checkpoints.{name}"
            for name in ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
        }
        required |= {
            f"lexi_reference.{name}"
            for name in ("words", "entries", "senses", "examples", "word_alternatives", "datasets")
        }
        existing = set(
            (
                await connection.execute(
                    text(
                        "SELECT schemaname || '.' || tablename FROM pg_tables "
                        "WHERE schemaname IN ('public', 'lexi', 'lexi_reference', 'checkpoints')"
                    )
                )
            ).scalars()
        )
        if not required <= existing:
            raise RuntimeError("schema_tables_missing; run the explicit migration gate")
        if not await connection.scalar(
            text("SELECT checksum FROM lexi_reference.datasets WHERE name='reference'")
        ):
            raise RuntimeError("reference_dataset_missing; run the explicit migration gate")
