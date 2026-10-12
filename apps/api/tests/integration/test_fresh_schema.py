import asyncio
import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from lexi_ai.migrations import inspect_head
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from pycil.account.models import UsageEvent, UsagePeriod
from pycil.account.plans import Feature, Plan
from pycil.account.usage import allowance, change_plan, settle
from pycil.migrate import CONTENT_PATH, migrate, migration_config
from pycil.study.models import UserSense


async def test_fresh_ordered_migrations_repeat_without_drift(database, content):
    engine, _, url = database
    await asyncio.to_thread(migrate, url, content_path=content)
    await asyncio.to_thread(command.check, migration_config(url))
    revisions = list(ScriptDirectory.from_config(migration_config(url)).walk_revisions())
    assert [(r.revision, r.down_revision) for r in revisions] == [
        ("20261012_profile", "20261011_learning"),
        ("20261011_learning", "20261009_baseline"),
        ("20261009_baseline", None),
    ]
    async with engine.connect() as connection:
        assert (
            await connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            == "20261012_profile"
        )
        assert (
            await connection.scalar(text("SELECT version_num FROM lexi.alembic_version"))
            == inspect_head()
        )
        assert not await connection.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='lexi' AND table_name='senses' "
                "AND column_name='usage_note')"
            )
        )
        names = (
            (
                await connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                )
            )
            .scalars()
            .all()
        )
        assert set(names) == {
            "alembic_version",
            "users",
            "usage_periods",
            "usage_events",
            "nodes",
            "node_paths",
            "deck_senses",
            "user_senses",
            "user_daily_activity",
            "review_log",
            "conversations",
        }


async def test_setup_imports_bundled_content_and_repeats_without_overwriting(
    database, no_inference
):
    engine, _, url = database
    with sqlite3.connect(CONTENT_PATH.as_uri() + "?mode=ro", uri=True) as source:
        expected_words = source.execute("SELECT count(*) FROM words").fetchone()[0]
        expected_senses = source.execute("SELECT count(*) FROM senses").fetchone()[0]
    await asyncio.to_thread(migrate, url)
    async with engine.begin() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM lexi.words")) == expected_words
        assert await connection.scalar(text("SELECT count(*) FROM lexi.senses")) == expected_senses
        await connection.execute(text("UPDATE lexi.words SET lemma='local edit' WHERE id=1"))
    await asyncio.to_thread(migrate, url)
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM lexi.words")) == expected_words
        assert (
            await connection.scalar(text("SELECT lemma FROM lexi.words WHERE id=1")) == "local edit"
        )
        assert set(
            (await connection.execute(text("SELECT name FROM lexi_reference.datasets"))).scalars()
        ) == {"reference", "content.lexi.words", "content.lexi.artifacts"}


async def test_user_settings_database_check(database, user):
    engine, _, _ = database
    with pytest.raises(IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE users SET settings='[]'::jsonb WHERE id=:id"), {"id": user.id}
            )


async def test_profile_migration_normalizes_legacy_names_and_enforces_shape(database, user):
    engine, _, url = database
    await asyncio.to_thread(command.downgrade, migration_config(url), "20261011_learning")
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE users SET display_name='  Legacy name  ' WHERE id=:id"), {"id": user.id}
        )
        await connection.execute(
            text(
                "INSERT INTO users(id,clerk_subject,display_name,plan,cycle_anchor,created_at) "
                "VALUES(:id,'legacy-blank','   ','FREE',now(),now())"
            ),
            {"id": uuid4()},
        )
    await asyncio.to_thread(command.upgrade, migration_config(url), "head")
    async with engine.connect() as connection:
        assert (
            await connection.scalar(
                text("SELECT display_name FROM users WHERE id=:id"), {"id": user.id}
            )
            == "Legacy name"
        )
        assert (
            await connection.scalar(
                text("SELECT display_name FROM users WHERE clerk_subject='legacy-blank'")
            )
            is None
        )
    with pytest.raises(IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE users SET display_name='' WHERE id=:id"), {"id": user.id}
            )


async def test_actual_lexi_sense_fk_rejects_synthetic_identity(database, user):
    _, sessions, _ = database
    now = datetime.now(UTC)
    with pytest.raises(IntegrityError) as caught:
        async with sessions() as session, session.begin():
            session.add(
                UserSense(
                    user_id=user.id,
                    sense_id=10_000_000,
                    stability=1.0,
                    difficulty=5.0,
                    last_exposure_at=now,
                    due_at=now,
                    elo=600,
                    review_count=1,
                    lapse_count=0,
                )
            )
    assert caught.value.orig.sqlstate == "23503"
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(UserSense)) == 0


async def test_usage_read_is_read_only_and_settlement_is_idempotent(database, user, config):
    _, sessions, _ = database
    now = datetime(2026, 3, 1, tzinfo=UTC)
    async with sessions() as session:
        result = await allowance(session, user, config, now)
        assert result["remaining_units"] == 1_000_000
        assert await session.scalar(select(func.count()).select_from(UsagePeriod)) == 0
    key = uuid4()

    async def submit():
        async with sessions() as session:
            return await settle(
                session,
                user.id,
                config,
                execution_key=key,
                feature=Feature.ASSISTANT,
                units=123,
                unmetered_calls=0,
                moment=now,
            )

    events = await asyncio.gather(submit(), submit(), submit())
    assert len({event.id for event in events}) == 1
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(UsageEvent)) == 1
        assert await session.scalar(select(UsagePeriod.used_units)) == 123
    async with sessions() as session:
        await change_plan(session, user.id, Plan.PRO, config, now)
    async with sessions() as session:
        period = await session.scalar(select(UsagePeriod))
        assert period.allowance_units == 10_000_000
        assert period.used_units == 123
