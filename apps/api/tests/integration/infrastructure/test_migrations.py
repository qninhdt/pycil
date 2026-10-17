import asyncio
import os
import sys

import pytest
from psycopg import AsyncConnection, sql

from pycil.app.migrate import MIGRATION_LOCK_KEY
from pycil.app.schema import verify_schema
from pycil.assistant.checkpoints import checkpoint_dsn
from tests.support.reference import reference_file, reference_word


@pytest.fixture
async def migration_clients(database):
    clients = []

    async def start(reference=None, *, code=None):
        arguments = (
            [sys.executable, "-c", code] if code else [sys.executable, "-m", "pycil.app.migrate"]
        )
        if reference is not None:
            arguments.extend(["--reference", str(reference)])
        process = await asyncio.create_subprocess_exec(
            *arguments,
            env={**os.environ, "DB_URL": database.url},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output = asyncio.create_task(process.communicate())
        clients.append((process, output))
        return process, output

    yield start
    for process, _output in clients:
        if process.returncode is None:
            process.kill()
    async with asyncio.timeout(10):
        await asyncio.gather(*(output for _, output in clients))


async def wait_for(connection, query, parameters=()):
    async with asyncio.timeout(10):
        while not (await (await connection.execute(query, parameters)).fetchone())[0]:
            await asyncio.sleep(0.01)


@pytest.mark.parametrize("crash_owner", [False, True])
async def test_migration_clients_serialize_through_import_and_recover_after_crash(
    crash_owner, database, migration_clients, tmp_path
):
    reference = reference_file(tmp_path / "reference.jsonl", [reference_word()])
    dsn = checkpoint_dsn(database.url)
    async with (
        await AsyncConnection.connect(dsn, connect_timeout=5) as blocker,
        await AsyncConnection.connect(dsn, autocommit=True, connect_timeout=5) as observer,
    ):
        await blocker.execute("LOCK TABLE public.reference_words IN ACCESS EXCLUSIVE MODE")
        first, first_output = await migration_clients(reference)
        # Block import after native checkpoint setup has crossed its autocommit boundaries.
        await wait_for(
            observer,
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_locks
                WHERE relation = 'public.reference_words'::regclass AND NOT granted
            )
        """,
        )
        owner = await observer.execute("""
            SELECT a.pid FROM pg_stat_activity a JOIN pg_locks l USING (pid)
            WHERE a.datname = current_database() AND a.application_name = 'pycil-migrate-lock'
                AND l.locktype = 'advisory' AND l.granted
        """)
        owner_pid = (await owner.fetchone())[0]
        second, second_output = await migration_clients(reference)
        await wait_for(
            observer,
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_stat_activity a JOIN pg_locks l USING (pid)
                WHERE a.datname = current_database()
                    AND a.application_name = 'pycil-migrate-lock'
                    AND l.locktype = 'advisory' AND NOT l.granted
            )
        """,
        )
        if crash_owner:
            first.kill()
            async with asyncio.timeout(10):
                await first_output
            assert first.returncode == -9
            await wait_for(
                observer,
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_stat_activity a JOIN pg_locks l USING (pid)
                    WHERE a.datname = current_database()
                        AND a.application_name = 'pycil-migrate-lock'
                        AND a.pid <> %s AND l.locktype = 'advisory' AND l.granted
                )
            """,
                (owner_pid,),
            )
        await blocker.rollback()
        async with asyncio.timeout(15):
            first_logs, second_logs = await asyncio.gather(first_output, second_output)
        assert second.returncode == 0, second_logs[0].decode()
        assert b"migration_completed" in second_logs[0]
        if not crash_owner:
            assert first.returncode == 0, first_logs[0].decode()
            assert b"migration_completed" in first_logs[0]
        assert not (
            await (
                await observer.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_stat_activity
                WHERE datname = current_database() AND application_name = 'pycil-migrate-lock'
            )
        """)
            ).fetchone()
        )[0]
    await verify_schema(database.engine)


async def test_migration_owner_wait_times_out_before_any_setup(database, migration_clients):
    async with await AsyncConnection.connect(
        checkpoint_dsn(database.url), autocommit=True, connect_timeout=5
    ) as owner:
        await owner.execute(
            "SELECT pg_advisory_lock(hashtextextended(%s, 0))", (MIGRATION_LOCK_KEY,)
        )
        process, output = await migration_clients(
            code="from pycil.app import migrate; migrate.LOCK_WAIT_SECONDS = 0.1; migrate.main()"
        )
        async with asyncio.timeout(10):
            logs, _ = await output
        assert process.returncode == 1
        assert b"migration_lock_timeout" in logs and b"migration_lock_acquired" not in logs
        assert b"Context impl" not in logs
    process, output = await migration_clients()
    async with asyncio.timeout(15):
        logs, _ = await output
    assert process.returncode == 0, logs.decode()


@pytest.mark.parametrize("table", ["alembic_version", "checkpoint_migrations"])
async def test_migration_stages_fail_within_their_sql_lock_deadline(
    table, database, migration_clients
):
    async with await AsyncConnection.connect(
        checkpoint_dsn(database.url), connect_timeout=5
    ) as blocker:
        await blocker.execute(
            sql.SQL("LOCK TABLE public.{} IN ACCESS EXCLUSIVE MODE").format(sql.Identifier(table))
        )
        process, output = await migration_clients()
        async with asyncio.timeout(12):
            logs, _ = await output
        assert process.returncode == 1
        assert b"migration_lock_acquired" in logs and b"setup_failed" in logs
        assert b"migration_completed" not in logs
        await blocker.rollback()
    process, output = await migration_clients()
    async with asyncio.timeout(15):
        logs, _ = await output
    assert process.returncode == 0, logs.decode()


@pytest.mark.parametrize("failure", ["missing_artifact", "deadline"])
async def test_failed_setup_releases_migration_ownership(
    failure, database, migration_clients, tmp_path
):
    reference = tmp_path / "reference.jsonl"
    code = None
    async with await AsyncConnection.connect(
        checkpoint_dsn(database.url), connect_timeout=5
    ) as blocker:
        if failure == "deadline":
            reference_file(reference, [reference_word()])
            await blocker.execute("LOCK TABLE public.reference_words IN ACCESS EXCLUSIVE MODE")
            code = (
                "from pycil.app import migrate; migrate.SETUP_TIMEOUT_SECONDS = 0.2; migrate.main()"
            )
        process, output = await migration_clients(reference, code=code)
        async with asyncio.timeout(15):
            logs, _ = await output
        assert process.returncode == 1
        assert b"migration_lock_acquired" in logs and b"setup_failed" in logs
        assert b"migration_completed" not in logs
        if failure == "deadline":
            assert b"TimeoutError" in logs
        else:
            assert b"FileNotFoundError" in logs
        await blocker.rollback()
    reference_file(reference, [reference_word()])
    process, output = await migration_clients(reference)
    async with asyncio.timeout(15):
        logs, _ = await output
    assert process.returncode == 0, logs.decode()
    await verify_schema(database.engine)
