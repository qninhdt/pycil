import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import select, text

from pycil.account.models import User
from pycil.migrate import migrate, migration_config
from pycil.study.models import DailyActivity, ReviewReceipt, UserSense
from pycil.study.reviews import review
from pycil.study.schemas import ReviewBatch


@pytest.mark.parametrize("database", ["0001_baseline", "0002_nodes_spaces_paths"], indirect=True)
async def test_populated_learning_upgrade_and_original_replay(database, senses, config):
    engine, sessions, url = database
    owner, key = uuid4(), uuid4()
    when = datetime(2026, 10, 6, 1, tzinfo=UTC)
    async with engine.begin() as connection:
        await connection.execute(
            text("""INSERT INTO users(id,clerk_subject,plan,settings,cycle_anchor,created_at)
            VALUES(:id,:subject,'FREE',CAST(:settings AS jsonb),:when,:when)"""),
            {
                "id": owner,
                "subject": str(owner),
                "when": when,
                "settings": '{"timezone":"America/New_York","learning":{"questions_per_sense":7}}',
            },
        )
        # No source membership: durable activity must still survive the upgrade.
        await connection.execute(
            text("""INSERT INTO sense_memory(user_id,sense_id,stability,difficulty,
            last_review_at,due_at,last_rating,review_count,lapse_count,created_at,updated_at)
            VALUES(:owner,1,12,5,:when,:when,'GOOD',4,1,:when,:when)"""),
            {"owner": owner, "when": when},
        )
        await connection.execute(
            text("""INSERT INTO review_log(user_id,event_key,sense_id,rating,
            accepted_at,applied,mastery_after,due_after)
            VALUES(:owner,:key,1,'GOOD',:when,true,50,:when)"""),
            {"owner": owner, "key": key, "when": when},
        )
    await asyncio.to_thread(migrate, url)
    await asyncio.to_thread(migrate, url)
    await asyncio.to_thread(command.check, migration_config(url))
    async with sessions() as session:
        user = await session.get(User, owner)
        assert user.settings["learning"] == {"questions_per_sense": 7, "max_sense_count": 4}
        assert user.handle is None and user.bio is None
        memory = await session.get(UserSense, (owner, 1))
        assert (
            memory.stability,
            memory.difficulty,
            memory.review_count,
            memory.lapse_count,
            memory.due_at,
        ) == (12, 5, 4, 1, when)
        receipt = await session.get(ReviewReceipt, (owner, key))
        assert receipt.activity_day.isoformat() == "2026-10-05"
        original = receipt.result
        assert "mastery_after" not in original["results"][0]
        daily = (await session.scalars(select(DailyActivity))).one()
        assert (daily.applied_events, daily.practice_events) == (1, 0)
        await session.rollback()
        assert (
            await review(
                session,
                owner,
                ReviewBatch(results=[{"sense_id": 1, "rating": "GOOD"}]),
                key,
                config,
            )
            == original
        )
        assert (await session.get(UserSense, (owner, 1))).review_count == 4


@pytest.mark.parametrize("database", ["0002_nodes_spaces_paths"], indirect=True)
async def test_invalid_old_settings_abort_atomically(database):
    engine, _, url = database
    owner = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            text("""INSERT INTO users(id,clerk_subject,plan,settings,cycle_anchor,created_at)
            VALUES(:id,:subject,'FREE',CAST(:settings AS jsonb),
            CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""),
            {
                "id": owner,
                "subject": str(owner),
                "settings": '{"learning":{"questions_per_sense":0}}',
            },
        )
    with pytest.raises(RuntimeError, match="Invalid legacy"):
        await asyncio.to_thread(command.upgrade, migration_config(url), "head")
    async with engine.connect() as connection:
        assert (
            await connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0002_nodes_spaces_paths"
        )
        assert await connection.scalar(text("SELECT to_regclass('user_senses')")) is None
        assert await connection.scalar(text("SELECT to_regclass('sense_memory')")) is not None
