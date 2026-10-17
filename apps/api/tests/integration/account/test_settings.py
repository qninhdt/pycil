import asyncio

import pytest

from pycil.account.models import User
from pycil.account.schemas import PreferencesPatch
from pycil.account.settings import preferences, update_preferences
from pycil.app.config import load_config
from pycil.app.http import status_for
from pycil.study.enums import ResponseFormat
from pycil.utils.errors import OperationError
from tests.support.account import account


async def test_concurrent_preference_patches_merge_and_invalid_changes_roll_back(database):
    config = load_config()
    user, _ = await account(database.sessions)

    async def patch(data):
        async with database.sessions() as session:
            return await update_preferences(
                session, user.id, PreferencesPatch(**data), config.account, config.study
            )

    await asyncio.gather(patch({"locale": "vi"}), patch({"assistant": {"auto_approve": True}}))
    with pytest.raises(OperationError) as error:
        await patch({"learning": {"formats": [ResponseFormat.SHORT_ANSWER]}})
    assert status_for(error.value) == 403
    with pytest.raises(OperationError) as error:
        await patch({"timezone": "invalid_timezone"})
    assert status_for(error.value) == 422
    async with database.sessions() as session:
        saved = await session.get(User, user.id)
        resolved = preferences(saved.settings, config.account, config.study)
        assert resolved.locale == "vi"
        assert resolved.assistant.auto_approve is True
        assert resolved.learning.formats == [ResponseFormat.SINGLE_CHOICE]
        assert "timezone" not in saved.settings
