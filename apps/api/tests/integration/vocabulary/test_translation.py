import asyncio

import pytest
from sqlalchemy import func, select

from pycil.vocabulary.errors import InvalidResourceError
from pycil.vocabulary.models import Translation
from pycil.vocabulary.translation import translate_text


class Translator:
    def __init__(self):
        self.calls = 0

    async def complete(self, instruction, data, schema):
        self.calls += 1
        assert "The bank opens." in data
        assert "[bank]" not in data
        return schema(content="Ngân hàng mở cửa.")


async def test_concurrent_translation_reuses_exact_unwrapped_text(database):
    provider = Translator()
    results = await asyncio.gather(
        translate_text(database.sessions, provider, "The [bank] opens.", "vi"),
        translate_text(database.sessions, provider, "The bank opens.", "vi"),
    )
    assert results == ["Ngân hàng mở cửa."] * 2
    assert provider.calls == 1
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Translation)) == 1
    with pytest.raises(InvalidResourceError):
        await translate_text(database.sessions, provider, "The [bank opens.", "vi")
    assert provider.calls == 1


async def test_translation_exact_identity_and_provider_failure_never_publish_partial_rows(database):
    class Provider:
        async def complete(self, instruction, data, schema):
            return schema(content="translated")

    provider = Provider()
    for text, language in [("Bank", "vi"), ("bank", "vi"), ("bank", "fr")]:
        assert await translate_text(database.sessions, provider, text, language) == "translated"

    class Failure:
        async def complete(self, *args):
            raise RuntimeError("unavailable")

    with pytest.raises(RuntimeError):
        await translate_text(database.sessions, Failure(), "different", "vi")
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Translation)) == 3
