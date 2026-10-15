"""Explicit PostgreSQL baseline, native checkpoint setup and optional JSONL import."""

import argparse
import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from pycil.assistant.checkpoints import setup_checkpoints
from pycil.infrastructure.database import connect, verify_schema
from pycil.infrastructure.observability import configure_logging, get_logger
from pycil.vocabulary.references.importer import import_reference


def migration_config(url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def migrate(url: str, *, reference_path: Path | None = None, baseline_content: bool = False):
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("Explicit PostgreSQL application URL required")
    command.upgrade(migration_config(url), "head")

    async def finish():
        await setup_checkpoints(url)
        engine, sessions = connect(url)
        try:
            if reference_path is not None:
                await import_reference(sessions, reference_path)
            if baseline_content:
                from pycil.infrastructure.content_revisions import baseline

                await baseline(sessions)
            await verify_schema(engine, require_reference=reference_path is not None)
        finally:
            await engine.dispose()

    asyncio.run(finish())


def main():
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DB_URL"))
    parser.add_argument("--reference", type=Path, help="Validated reference JSONL artifact")
    parser.add_argument(
        "--baseline-content",
        action="store_true",
        help="Baseline existing content with content writes paused",
    )
    arguments = parser.parse_args()
    if not arguments.database_url:
        parser.error("--database-url or DB_URL is required")
    try:
        migrate(
            arguments.database_url,
            reference_path=arguments.reference,
            baseline_content=arguments.baseline_content,
        )
    except Exception as error:
        get_logger(__name__).error("setup_failed", error_type=type(error).__name__)
        parser.exit(1, "Setup failed; check connectivity, schema and reference validation.\n")


if __name__ == "__main__":
    main()
