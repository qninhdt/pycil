"""Explicit one-shot Lexi → Pycil gate; never run from API startup."""

import argparse
import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from lexi_ai import Lexicon
from lexi_ai.migrations import upgrade_to_head

from pycil.assistant.checkpoints import setup_checkpoints
from pycil.database import connect, verify_schema

CONTENT_PATH = Path(__file__).resolve().parents[3] / "vendor/lexi-ai/content.sqlite"


def migration_config(url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def migrate(
    url: str,
    *,
    reference_path: str | Path | None = None,
    content_path: str | Path = CONTENT_PATH,
):
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("Explicit PostgreSQL application database URL required")
    upgrade_to_head(url, db_schema="lexi")
    command.upgrade(migration_config(url), "head")

    async def finish():
        lexicon = Lexicon(db_url=url, db_schema="lexi")
        try:
            await lexicon.import_reference(reference_path)
            await lexicon.import_content(content_path)
        finally:
            await lexicon.close()
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
    parser.add_argument("--reference", type=Path, help="Optional offline reference.sqlite artifact")
    parser.add_argument(
        "--content", type=Path, default=CONTENT_PATH, help="Bundled content.sqlite artifact"
    )
    arguments = parser.parse_args()
    if not arguments.database_url:
        parser.error("--database-url or DB_URL is required")
    try:
        migrate(
            arguments.database_url,
            reference_path=arguments.reference,
            content_path=arguments.content,
        )
    except Exception:
        parser.exit(1, "Migration gate failed; verify target, connectivity and schema versions.\n")


if __name__ == "__main__":
    main()
