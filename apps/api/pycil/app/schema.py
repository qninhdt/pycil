"""Application schema verification and domain model registration."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from pycil.infrastructure.database import Base
from pycil.observability import get_logger

logger = get_logger("pycil.app.schema")


def migration_config(url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def register_models():
    from pycil.account import models as account
    from pycil.assistant import models as assistant
    from pycil.library import models as library
    from pycil.study import models as study
    from pycil.themes import models as themes
    from pycil.vocabulary import models as vocabulary
    from pycil.vocabulary import revisions as content_revisions
    from pycil.vocabulary.references import models as reference

    return account, assistant, library, study, themes, vocabulary, reference, content_revisions


async def verify_schema(engine: AsyncEngine, *, require_reference: bool = True) -> None:
    """Read-only gate; missing or obsolete tables are never repaired on startup."""
    register_models()
    head = ScriptDirectory.from_config(migration_config("postgresql+asyncpg://")).get_current_head()
    try:
        async with engine.connect() as connection:
            versions = (
                (await connection.execute(text("SELECT version_num FROM public.alembic_version")))
                .scalars()
                .all()
            )
            native = (
                (
                    await connection.execute(
                        text("SELECT v FROM public.checkpoint_migrations ORDER BY v")
                    )
                )
                .scalars()
                .all()
            )
            if versions != [head] or native != list(range(len(AsyncPostgresSaver.MIGRATIONS))):
                raise RuntimeError("schema_version_mismatch; run the explicit setup command")
            required = set(Base.metadata.tables) | {
                "checkpoints",
                "checkpoint_blobs",
                "checkpoint_writes",
            }
            existing = set(
                (
                    await connection.execute(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                ).scalars()
            )
            if not required <= existing:
                raise RuntimeError("schema_tables_missing; run the explicit setup command")
            if require_reference and not await connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM reference_words)")
            ):
                raise RuntimeError("reference_dataset_missing; import reference JSONL explicitly")
        logger.info("schema_verification_passed")
    except Exception as error:
        logger.error("schema_verification_failed", error_type=type(error).__name__)
        raise
