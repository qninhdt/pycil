import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from pycil.account.models import UsageEvent, UsagePeriod, User
from pycil.account.plans import Feature, Plan
from pycil.account.profiles import public_projection, update_profile
from pycil.account.schemas import ProfilePatch
from pycil.account.usage import admit, allowance, change_plan, settle
from pycil.app.config import load_config
from pycil.utils.errors import OperationError
from tests.support.account import account


async def test_concurrent_handle_claims_have_one_winner_and_atomic_loser(database):
    users = [(await account(database.sessions))[0] for _ in range(2)]
    barrier = asyncio.Barrier(2)

    async def claim(user):
        await barrier.wait()
        async with database.sessions() as session:
            return await update_profile(
                session, user.id, ProfilePatch(handle="shared_handle", bio="winner")
            )

    results = await asyncio.gather(*(claim(user) for user in users), return_exceptions=True)
    assert sum(isinstance(result, User) for result in results) == 1
    errors = [result for result in results if isinstance(result, OperationError)]
    assert len(errors) == 1 and errors[0].code == "handle_unavailable"
    async with database.sessions() as session:
        saved = list(await session.scalars(select(User)))
        loser = next(user for user in saved if user.handle != "shared_handle")
        assert loser.bio is None
        projection = await public_projection(
            next(user for user in saved if user.handle == "shared_handle"), session
        )
        assert set(projection) == {
            "id",
            "display_name",
            "handle",
            "bio",
            "joined_at",
            "published_node_id",
        }


async def test_allowance_read_is_readonly_and_plan_changes_keep_current_cycle_budget(database):
    config = load_config().account
    user, _ = await account(database.sessions)
    moment = datetime.now(UTC)
    async with database.sessions() as session:
        budget = await allowance(session, user, config, moment)
        assert budget["used_units"] == 0
        assert await session.scalar(select(func.count()).select_from(UsagePeriod)) == 0
    async with database.sessions() as session:
        await settle(
            session,
            user.id,
            config,
            execution_key=uuid4(),
            feature=Feature.ASSISTANT,
            units=1,
            unmetered_calls=0,
            moment=moment,
        )
    for plan in [Plan.PRO, Plan.FREE]:
        async with database.sessions() as session:
            await change_plan(session, user.id, plan, config, moment)
    async with database.sessions() as session:
        current = await session.get(User, user.id)
        budget = await allowance(session, current, config, moment)
        assert current.plan is Plan.FREE
        assert budget["allowance_units"] == config.plans[Plan.PRO].monthly_allowance_units
        assert budget["remaining_units"] == budget["allowance_units"] - 1


async def test_cross_user_usage_replay_is_rejected_and_admission_rechecks_current_plan(database):
    config = load_config().account
    user, _ = await account(database.sessions)
    other, _ = await account(database.sessions)
    moment, key = datetime.now(UTC), uuid4()
    async with database.sessions() as session:
        await settle(
            session,
            user.id,
            config,
            execution_key=key,
            feature=Feature.ASSISTANT,
            units=0,
            unmetered_calls=1,
            moment=moment,
        )
    async with database.sessions() as session:
        with pytest.raises(OperationError) as error:
            await settle(
                session,
                other.id,
                config,
                execution_key=key,
                feature=Feature.ASSISTANT,
                units=0,
                unmetered_calls=1,
                moment=moment,
            )
        assert error.value.code == "usage_event_conflict"
    async with database.sessions() as session:
        with pytest.raises(OperationError) as error:
            await admit(session, user.id, config, Feature.ADVANCED_GRADING, moment)
        assert error.value.code == "feature_not_available"
    async with database.sessions() as session:
        await change_plan(session, user.id, Plan.PRO, config, moment)
    async with database.sessions() as session:
        assert await admit(session, user.id, config, Feature.ADVANCED_GRADING, moment) is Plan.PRO


async def test_exhausted_allowance_denies_new_work_without_creating_extra_events(database):
    config = load_config().account
    user, _ = await account(database.sessions)
    moment = datetime.now(UTC)
    quota = config.plans[user.plan].monthly_allowance_units
    async with database.sessions() as session:
        await settle(
            session,
            user.id,
            config,
            execution_key=uuid4(),
            feature=Feature.ASSISTANT,
            units=quota,
            unmetered_calls=0,
            moment=moment,
        )
    async with database.sessions() as session:
        with pytest.raises(OperationError) as error:
            await admit(session, user.id, config, Feature.ASSISTANT, moment)
        assert error.value.code == "allowance_exhausted"
    async with database.sessions() as session:
        budget = await allowance(session, user, config, moment)
        assert budget["used_units"] == quota and budget["remaining_units"] == 0
        assert await session.scalar(select(func.count()).select_from(UsagePeriod)) == 1
        assert await session.scalar(select(func.count()).select_from(UsageEvent)) == 1
