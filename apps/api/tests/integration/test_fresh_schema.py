import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from pycil.account.models import UsageEvent, UsagePeriod
from pycil.account.plans import Feature, Plan
from pycil.account.usage import allowance, change_plan, settle
from pycil.migrate import migrate, migration_config
from pycil.study.models import Rating, UserSense


async def test_fresh_ordered_migrations_repeat_without_drift(database):
    engine, _, url = database
    await asyncio.to_thread(migrate, url)
    await asyncio.to_thread(command.check, migration_config(url))
    async with engine.connect() as connection:
        assert (
            await connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            == "0005_profile_handle_bio"
        )
        assert (
            await connection.scalar(text("SELECT version_num FROM lexi.alembic_version"))
            == "20261003_base"
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
            "word_generations",
            "conversations",
        }


async def test_user_settings_database_check(database, user):
    engine, _, _ = database
    with pytest.raises(IntegrityError):
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE users SET settings='[]'::jsonb WHERE id=:id"), {"id": user.id}
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
                    last_review_at=now,
                    due_at=now,
                    last_rating=Rating.GOOD,
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
