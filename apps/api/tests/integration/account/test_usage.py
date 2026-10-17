import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from pycil.account.models import UsageEvent, UsagePeriod
from pycil.account.plans import Feature
from pycil.account.usage import settle
from pycil.app.config import load_config
from pycil.app.http import status_for
from pycil.utils.errors import OperationError
from tests.support.account import account


async def test_concurrent_usage_replay_charges_once_and_conflicts_roll_back(database):
    config = load_config().account
    user, _ = await account(database.sessions)
    key, moment = uuid4(), datetime.now(UTC)
    barrier = asyncio.Barrier(2)

    async def charged(units=17, unmetered_calls=1):
        async with database.sessions() as session:
            return await settle(
                session,
                user.id,
                config,
                execution_key=key,
                feature=Feature.ASSISTANT,
                units=units,
                unmetered_calls=unmetered_calls,
                moment=moment,
            )

    async def simultaneous_charge():
        await barrier.wait()
        return await charged()

    first, replay = await asyncio.gather(simultaneous_charge(), simultaneous_charge())
    assert first.id == replay.id
    with pytest.raises(OperationError) as error:
        await charged(units=18)
    assert status_for(error.value) == 409
    with pytest.raises(ValueError):
        await charged(unmetered_calls=True)
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(UsageEvent)) == 1
        period = await session.scalar(select(UsagePeriod))
        assert period.used_units == 17
