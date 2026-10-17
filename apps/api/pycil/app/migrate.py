"""Explicit PostgreSQL baseline, native checkpoint setup and optional JSONL import."""

import argparse
import asyncio
import os
from pathlib import Path

from alembic import command
from psycopg import Connection
from psycopg.errors import LockNotAvailable

from pycil.app.schema import migration_config, verify_schema
from pycil.assistant.checkpoints import checkpoint_dsn, setup_checkpoints
from pycil.infrastructure.database import connect
from pycil.observability import configure_logging, get_logger
from pycil.vocabulary.references.importer import import_reference

logger = get_logger(__name__)
MIGRATION_LOCK_KEY = "pycil:migration"
LOCK_WAIT_SECONDS = 60
SETUP_TIMEOUT_SECONDS = 600


def migrate(url: str, *, reference_path: Path | None = None, baseline_content: bool = False):
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("Explicit PostgreSQL application URL required")

    async def finish():
        async with asyncio.timeout(SETUP_TIMEOUT_SECONDS):
            await setup_checkpoints(url)
            engine, sessions = connect(url)
            try:
                if reference_path is not None:
                    await import_reference(sessions, reference_path)
                if baseline_content:
                    from pycil.vocabulary.revisions import baseline

                    await baseline(sessions)
                await verify_schema(engine, require_reference=reference_path is not None)
            finally:
                await engine.dispose()

    # A dedicated session keeps ownership across DDL and native autocommit boundaries.
    with Connection.connect(
        checkpoint_dsn(url),
        autocommit=True,
        connect_timeout=5,
        application_name="pycil-migrate-lock",
        options=(
            f"-c lock_timeout={LOCK_WAIT_SECONDS}s "
            f"-c statement_timeout={LOCK_WAIT_SECONDS + 5}s -c idle_session_timeout=0"
        ),
    ) as ownership:
        logger.info("migration_lock_waiting")
        try:
            ownership.execute(
                "SELECT pg_advisory_lock(hashtextextended(%s, 0))", (MIGRATION_LOCK_KEY,)
            )
        except LockNotAvailable:
            logger.error("migration_lock_timeout")
            raise TimeoutError("Migration ownership wait timed out") from None
        logger.info("migration_lock_acquired")
        command.upgrade(migration_config(url), "head")
        asyncio.run(finish())
        logger.info("migration_completed")


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
