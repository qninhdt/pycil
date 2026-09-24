"""The single Alembic baseline creates the schema represented by the models."""

import os
import subprocess
import sys
import tempfile

import asyncpg
from testcontainers.postgres import PostgresContainer


def test_baseline_upgrade_and_autogenerate_are_clean():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as postgres:
        db_url = postgres.get_connection_url()
        env = os.environ | {"DB_URL": db_url}

        upgrade = _alembic(env, "upgrade", "head")
        assert upgrade.returncode == 0, upgrade.stderr

        check = _alembic(env, "check")
        assert check.returncode == 0, check.stderr
        assert "No new upgrade operations detected" in check.stdout

        snapshot = _snapshot(db_url)

    assert snapshot == {
        # The head of the chain, not the baseline: the chain is what a fresh
        # deployment actually runs, and pinning the baseline would let a later
        # revision silently change the resulting schema.
        "revision": "0008_credit_debit_usage_snapshot",
        "tables": {
            "assistant_threads",
            "credit_debits",
            "deck_senses",
            "nodes",
            "responses",
            "review_log",
            "session_summaries",
            "user_credits",
            "user_learning_settings",
            "user_sense_stats",
            "users",
        },
        # Leak detector, not a wish list: `retired_tables` reports tables from the
        # watch set that are still present, so empty is the correct result and a
        # non-empty set means a migration failed to drop one. The queue tables and
        # the legacy auth tables are watched in `_read_snapshot`.
        "retired_tables": set(),
    }


def test_baseline_dump_restores_into_an_empty_postgres():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as source:
        source_url = source.get_connection_url()
        env = os.environ | {"DB_URL": source_url}
        upgrade = _alembic(env, "upgrade", "head")
        assert upgrade.returncode == 0, upgrade.stderr

        with PostgresContainer("postgres:16-alpine", driver="asyncpg") as target:
            target_url = target.get_connection_url()
            with tempfile.NamedTemporaryFile(suffix=".dump") as dump:
                dumped = subprocess.run(
                    [
                        "pg_dump",
                        "--format=custom",
                        "--no-owner",
                        "--file",
                        dump.name,
                        _sync_url(source_url),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                assert dumped.returncode == 0, dumped.stderr
                restored = subprocess.run(
                    [
                        "pg_restore",
                        "--clean",
                        "--if-exists",
                        "--no-owner",
                        "--dbname",
                        _sync_url(target_url),
                        dump.name,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                assert restored.returncode == 0, restored.stderr
                snapshot = _snapshot(target_url)

    assert snapshot["revision"] == "0008_credit_debit_usage_snapshot"
    assert "users" in snapshot["tables"]


def _alembic(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )


def _snapshot(db_url: str) -> dict[str, object]:
    import asyncio

    return asyncio.run(_read_snapshot(db_url))


def _sync_url(db_url: str) -> str:
    return db_url.replace("postgresql+asyncpg://", "postgresql://")


async def _read_snapshot(db_url: str) -> dict[str, object]:
    connection = await asyncpg.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        revision = await connection.fetchval("SELECT version_num FROM alembic_version")
        tables = {
            row[0]
            for row in await connection.fetch(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                  AND table_name <> 'alembic_version'
                """
            )
        }
        retired = tables & {
            "async_tasks",
            "async_task_deliveries",
            "assistant_run_events",
            "assistant_actions",
            "assistant_action_audit",
            "session_sense_attempts",
            "deck_attributes",
            # Retired by the Clerk and Redis-broker cutovers. A migration that
            # fails to drop one leaves it here, and the assertion below catches
            # it rather than letting a dead table survive unnoticed.
            "external_identities",
            "refresh_sessions",
            "job_command_receipts",
            "job_interests",
            "job_tasks",
        }
        return {"revision": revision, "tables": tables, "retired_tables": retired}
    finally:
        await connection.close()
