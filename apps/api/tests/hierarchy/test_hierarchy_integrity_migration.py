"""Migration coverage for the additive hierarchy-integrity revision."""

import asyncio
import os
import subprocess
import sys

import asyncpg
from testcontainers.postgres import PostgresContainer


def test_upgrade_from_baseline_adds_integrity_guards_then_removes_legacy_schema():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as postgres:
        db_url = postgres.get_connection_url()
        env = os.environ | {"DB_URL": db_url}
        _alembic(env, "0001_baseline")
        _alembic(env, "0008_assistant_agent")
        asyncio.run(_old_shape_write_still_succeeds(db_url))
        asyncio.run(_old_response_write_still_succeeds(db_url))
        _alembic(env, "head")
        rollback = _run_alembic(env, "0001_baseline", direction="downgrade")

        (
            generation,
            target_index,
            target_constraint,
            grading_schema,
            history_index,
            grading_check,
            legacy_schema_removed,
        ) = asyncio.run(_inspect(db_url))

    assert generation
    assert target_index
    assert target_constraint
    assert grading_schema
    assert history_index
    assert grading_check
    assert legacy_schema_removed
    # Canonicalization is forward-only: a rollback must not restore removed
    # product features and their persisted data model.
    assert rollback.returncode != 0
    assert "forward-only" in rollback.stderr


def test_upgrade_reports_invalid_legacy_membership():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as postgres:
        db_url = postgres.get_connection_url()
        env = os.environ | {"DB_URL": db_url}
        _alembic(env, "0001_baseline")
        asyncio.run(_insert_folder_membership(db_url))
        completed = _run_alembic(env, "head")

    assert completed.returncode != 0
    assert "membership on non-deck" in completed.stderr


def _alembic(env: dict[str, str], revision: str) -> None:
    completed = _run_alembic(env, revision)
    assert completed.returncode == 0, completed.stderr


def _run_alembic(
    env: dict[str, str], revision: str, *, direction: str = "upgrade"
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", direction, revision],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )


async def _insert_folder_membership(db_url: str) -> None:
    connection = await asyncpg.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        owner_id = await connection.fetchval(
            "INSERT INTO users (email, role, token_version) VALUES ($1, 'user', 0) RETURNING id",
            "migration-owner@example.com",
        )
        folder_id = await connection.fetchval(
            """
            INSERT INTO nodes (
                author_id, type, name, visibility, sense_count, like_count, fork_count
            ) VALUES ($1, 'FOLDER', 'invalid membership folder', 'PRIVATE', 0, 0, 0)
            RETURNING id
            """,
            owner_id,
        )
        await connection.execute(
            "INSERT INTO deck_senses (id, node_id, sense_id, position) VALUES (1, $1, 88, 0)",
            folder_id,
        )
    finally:
        await connection.close()


async def _old_shape_write_still_succeeds(db_url: str) -> None:
    connection = await asyncpg.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        owner_id = await connection.fetchval(
            "INSERT INTO users (email, role, token_version) VALUES ($1, 'user', 0) RETURNING id",
            "old-code-owner@example.com",
        )
        generation = await connection.fetchval(
            """
            INSERT INTO nodes (
                author_id, type, name, visibility, sense_count, like_count, fork_count
            ) VALUES ($1, 'DECK', 'old writer deck', 'PRIVATE', 0, 0, 0)
            RETURNING structural_generation
            """,
            owner_id,
        )
    finally:
        await connection.close()

    assert generation == 0


async def _old_response_write_still_succeeds(db_url: str) -> None:
    """An old API image can keep writing its pre-expand response shape."""
    connection = await asyncpg.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        owner_id = await connection.fetchval(
            "INSERT INTO users (email, role, token_version) VALUES ($1, 'user', 0) RETURNING id",
            "old-response-owner@example.com",
        )
        response_id = await connection.fetchval(
            """
            INSERT INTO responses (
                user_id, sense_id, question_id, is_correct, grade_status,
                grade_score, grade_feedback
            ) VALUES ($1, 11, 'legacy-question', true, 'graded', 1.0, 'legacy writer')
            RETURNING id
            """,
            owner_id,
        )
        row = await connection.fetchrow(
            "SELECT grade_status, grade_feedback FROM responses WHERE id = $1", response_id
        )
    finally:
        await connection.close()

    assert dict(row) == {"grade_status": "graded", "grade_feedback": "legacy writer"}


async def _inspect(db_url: str) -> tuple[bool, bool, bool, bool, bool, bool, bool]:
    connection = await asyncpg.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        generation = await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'nodes' AND column_name = 'structural_generation'
            )
            """
        )
        target_index = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_nodes_target_node_id')"
        )
        target_constraint = await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_nodes_reference_target_shape'
            )
            """
        )
        grading_schema = await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'session_sense_attempts'
            ) AND EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'responses' AND column_name = 'raw_answer'
            )
            """
        )
        history_index = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_indexes "
            "WHERE indexname = 'idx_review_log_user_sense_time')"
        )
        grading_check = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_constraint "
            "WHERE conname = 'ck_responses_pending_has_raw_answer')"
        )
        legacy_schema_removed = await connection.fetchval(
            """
            SELECT NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE (table_name = 'users' AND column_name IN ('role', 'banned_at', 'ban_reason'))
                   OR (
                       table_name = 'nodes'
                       AND column_name IN ('sense_count', 'like_count', 'fork_count')
                   )
            )
            AND NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name IN ('folder_attributes', 'user_nodes')
            )
            """
        )
        return (
            generation,
            target_index,
            target_constraint,
            grading_schema,
            history_index,
            grading_check,
            legacy_schema_removed,
        )
    finally:
        await connection.close()
