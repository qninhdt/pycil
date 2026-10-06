"""Explicit one-shot Lexi → Pycil gate; never run from API/worker startup."""

import argparse
import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from lexi_ai.migrations import upgrade_to_head

from pycil.assistant.checkpoints import setup_checkpoints
from pycil.database import connect, verify_schema


def migration_config(url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def migrate(url: str):
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("Explicit PostgreSQL application database URL required")
    upgrade_to_head(url, db_schema="lexi")
    command.upgrade(migration_config(url), "head")

    async def finish():
        await setup_checkpoints(url)
        engine, _ = connect(url)
        try:
            await verify_schema(engine)
        finally:
            await engine.dispose()

    asyncio.run(finish())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DB_URL"))
    arguments = parser.parse_args()
    if not arguments.database_url:
        parser.error("--database-url or DB_URL is required")
    try:
        migrate(arguments.database_url)
    except Exception:
        parser.exit(1, "Migration gate failed; verify target, connectivity and schema versions.\n")


if __name__ == "__main__":
    main()
