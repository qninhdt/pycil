import asyncio

import pytest

from pycil.account.models import User
from pycil.account.schemas import PreferencesPatch
from pycil.account.settings import preferences, update_preferences
from pycil.app.config import load_config
from pycil.app.http import Problem
from pycil.study.enums import ResponseFormat
from tests.support.account import account


async def test_concurrent_preference_patches_merge_and_invalid_changes_roll_back(database):
    config = load_config()
    user, _ = await account(database.sessions)

    async def patch(data):
        async with database.sessions() as session:
            return await update_preferences(session, user.id, PreferencesPatch(**data), config)

    await asyncio.gather(patch({"locale": "vi"}), patch({"assistant": {"auto_approve": True}}))
    with pytest.raises(Problem) as error:
        await patch({"learning": {"formats": [ResponseFormat.SHORT_ANSWER]}})
    assert error.value.status == 403
    with pytest.raises(Problem) as error:
        await patch({"timezone": "invalid_timezone"})
    assert error.value.status == 422
    async with database.sessions() as session:
        saved = await session.get(User, user.id)
        resolved = preferences(saved.settings, config)
        assert resolved.locale == "vi"
        assert resolved.assistant.auto_approve is True
        assert resolved.learning.formats == [ResponseFormat.SINGLE_CHOICE]
        assert "timezone" not in saved.settings
