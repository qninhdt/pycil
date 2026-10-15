import pytest
from sqlalchemy import func, select

from pycil.infrastructure.kv_store import InMemoryStore
from pycil.study.artifacts.schemas import Artifact
from pycil.study.artifacts.storage import append, get_many, retrieve_many
from pycil.study.enums import QuestionArtifactType
from pycil.themes.errors import InvalidThemeError
from pycil.themes.service import create_theme, delete_theme, update_theme
from pycil.vocabulary.errors import InvalidOutputError, InvalidResourceError
from pycil.vocabulary.generation.themed import ensure_word_theme
from pycil.vocabulary.models import Definition, Example
from pycil.vocabulary.words import get_word
from tests.support.artifacts import payloads
from tests.support.vocabulary import neutral_word


class ThemeProvider:
    def __init__(self, *, invalid=False):
        self.calls, self.invalid = 0, invalid

    async def complete(self, instruction, data, schema, **options):
        self.calls += 1
        if schema.__name__ == "ThemeParts":
            return schema(voice="a spaceship crew", diction="clear and curious")
        return schema(
            senses=[
                {
                    "definition": "an institution holding the crew's money",
                    "examples": [
                        "The crew visits the [moon]."
                        if self.invalid
                        else "The crew visits the [bank]."
                    ],
                }
            ]
        )


async def test_theme_edits_preserve_content_and_deletion_removes_only_theme_namespace(database):
    word_id, _sense_id = await neutral_word(database.sessions)
    provider, store = ThemeProvider(), InMemoryStore(max_entries=1024, ttl=30)
    theme = await create_theme(database.sessions, provider, "Space", "Space", "life in space")
    themed = await ensure_word_theme(
        database.sessions, provider, word_id, theme.key, 1, word_store=store
    )
    assert themed.senses[0].definition.content == "an institution holding the crew's money"
    assert themed.senses[0].definition.theme_id == theme.id
    await update_theme(database.sessions, theme.key, voice="a station crew")
    reused = await ensure_word_theme(
        database.sessions, provider, word_id, theme.key, 1, word_store=store
    )
    assert reused == themed
    assert provider.calls == 2
    assert await delete_theme(database.sessions, theme.key, word_store=store)
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Definition)) == 1
        assert await session.scalar(select(func.count()).select_from(Example)) == 1
    neutral = await get_word(database.sessions, word_id, word_store=store)
    assert neutral.senses[0].definition.content == "a financial institution"
    with pytest.raises(InvalidResourceError):
        await get_word(database.sessions, word_id, theme_key=theme.key, word_store=store)
    with pytest.raises(InvalidThemeError):
        await update_theme(database.sessions, " ", voice="another voice")


async def test_invented_themed_target_never_publishes_partial_namespace(database):
    word_id, _sense_id = await neutral_word(database.sessions)
    provider = ThemeProvider(invalid=True)
    theme = await create_theme(database.sessions, provider, "space", "Space", "life in space")
    with pytest.raises(InvalidOutputError):
        await ensure_word_theme(database.sessions, provider, word_id, theme.key, 1)
    assert await get_word(database.sessions, word_id, theme_key=theme.key) is None
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Definition)) == 1


async def test_concurrent_theme_creation_has_one_identity_and_duplicate_loser(database):
    import asyncio

    from pycil.themes.models import Theme

    gate = asyncio.Barrier(2)

    class Provider:
        async def complete(self, instruction, data, schema):
            await gate.wait()
            return schema(voice="a spaceship crew", diction="clear and curious")

    async def create(key):
        return await create_theme(database.sessions, Provider(), key, "Space", "space travel")

    outcomes = await asyncio.gather(create("Space"), create(" SPACE "), return_exceptions=True)
    assert sum(isinstance(outcome, InvalidThemeError) for outcome in outcomes) == 1
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Theme)) == 1


async def test_theme_deletion_invalidates_both_caches_and_preserves_other_banks(database):
    word_id, sense_id = await neutral_word(database.sessions)
    provider = ThemeProvider()
    content, artifacts = (
        InMemoryStore(max_entries=1024, ttl=30),
        InMemoryStore(max_entries=1024, ttl=30),
    )
    themes = [
        await create_theme(database.sessions, provider, key, key, "life in space")
        for key in ["space", "station"]
    ]
    words = [
        await ensure_word_theme(
            database.sessions, provider, word_id, theme.key, 1, word_store=content
        )
        for theme in themes
    ]
    kind = QuestionArtifactType.CONTEXT_TO_WORD
    saved = await append(
        database.sessions,
        [
            Artifact(
                id=0,
                sense_id=sense_id,
                theme_id=theme.id,
                artifact_type=kind,
                payload=payloads()[kind],
            )
            for theme in themes
        ],
    )
    await get_many(database.sessions, [item.id for item in saved], store=artifacts)
    for theme in themes:
        sampled = await retrieve_many(
            database.sessions, [(sense_id, kind, 1)], theme_key=theme.key, store=artifacts
        )
        assert [item.theme_id for item in sampled] == [theme.id]
    assert await delete_theme(
        database.sessions, themes[0].key, word_store=content, artifact_store=artifacts
    )
    remaining = await get_many(database.sessions, [item.id for item in saved], store=artifacts)
    assert [item.theme_id for item in remaining] == [themes[1].id]
    assert (
        await get_word(database.sessions, word_id, theme_key=themes[1].key, word_store=content)
        == words[1]
    )
    with pytest.raises(InvalidResourceError):
        await get_word(database.sessions, word_id, theme_key=themes[0].key, word_store=content)
    assert (await get_word(database.sessions, word_id, word_store=content)).senses[
        0
    ].definition.theme_id is None


async def test_failed_theme_descriptor_generation_stores_no_theme(database):
    from pycil.themes.models import Theme

    class FailedProvider:
        async def complete(self, *args, **options):
            raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await create_theme(database.sessions, FailedProvider(), "space", "Space", "space travel")
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Theme)) == 0
