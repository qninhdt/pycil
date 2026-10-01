"""The single Alembic baseline creates the schema represented by the models."""

import os
import subprocess
import sys

import asyncpg
from sqlalchemy.engine import make_url
from testcontainers.postgres import PostgresContainer


def test_baseline_upgrade_and_autogenerate_are_clean():
    with PostgresContainer("postgres:18-alpine", driver="asyncpg") as postgres:
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
        "revision": "0001_baseline",
        "tables": {
            "account_plans",
            "assistant_threads",
            "deck_senses",
            "nodes",
            "responses",
            "review_log",
            "session_summaries",
            "study_session",
            "usage_events",
            "usage_periods",
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
    with PostgresContainer("postgres:18-alpine", driver="asyncpg") as source:
        source_url = source.get_connection_url()
        env = os.environ | {"DB_URL": source_url}
        upgrade = _alembic(env, "upgrade", "head")
        assert upgrade.returncode == 0, upgrade.stderr

        with PostgresContainer("postgres:18-alpine", driver="asyncpg") as target:
            target_url = target.get_connection_url()
            source_db = make_url(source_url)
            target_db = make_url(target_url)
            # Use the PostgreSQL 18 clients inside the containers, not whichever
            # older pg_dump/pg_restore happens to be installed on the host.
            dumped = subprocess.run(
                [
                    "docker",
                    "exec",
                    source.get_wrapped_container().id,
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "-U",
                    source_db.username,
                    "-d",
                    source_db.database,
                ],
                check=False,
                capture_output=True,
            )
            assert dumped.returncode == 0, dumped.stderr.decode(errors="replace")
            restored = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    target.get_wrapped_container().id,
                    "pg_restore",
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "-U",
                    target_db.username,
                    "-d",
                    target_db.database,
                ],
                input=dumped.stdout,
                check=False,
                capture_output=True,
            )
            assert restored.returncode == 0, restored.stderr.decode(errors="replace")
            snapshot = _snapshot(target_url)

    assert snapshot["revision"] == "0001_baseline"
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
            "account_plan_state",
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
            "user_credits",
            "credit_debits",
        }
        return {"revision": revision, "tables": tables, "retired_tables": retired}
    finally:
        await connection.close()
