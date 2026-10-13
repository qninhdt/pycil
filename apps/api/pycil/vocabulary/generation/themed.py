from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.infrastructure.database import transaction_lock
from pycil.infrastructure.llm import render_prompt
from pycil.themes.models import Theme
from pycil.themes.namespace import normalize_key
from pycil.vocabulary.cache import ContentCache
from pycil.vocabulary.errors import InvalidOutputError, InvalidResourceError
from pycil.vocabulary.models import Definition, Example, Word
from pycil.vocabulary.schemas import Word as WordSchema
from pycil.vocabulary.text import marked_occurrences, target_sequences
from pycil.vocabulary.words import get_word


class ThemedWordProvider(Protocol):
    async def complete(
        self, instruction: str, data: str, schema: type[ThemedWord]
    ) -> ThemedWord: ...


class ThemedSense(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: str = Field(min_length=1, max_length=16000)
    examples: list[str]

    @field_validator("definition")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("definition must not be blank")
        return value


class ThemedWord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    senses: list[ThemedSense]


async def ensure_word_theme(
    sessions: async_sessionmaker[AsyncSession],
    structured_llm: ThemedWordProvider,
    word_id: int,
    key: str,
    example_count: int,
    *,
    cache: ContentCache | None = None,
) -> WordSchema | None:
    if type(example_count) is not int or not 1 <= example_count <= 20:
        raise ValueError("invalid example count")
    key = normalize_key(key)
    async with sessions() as session, session.begin():
        await transaction_lock(session, f"word_theme:{word_id}:{key}")
        theme = await session.scalar(select(Theme).where(Theme.key == key).with_for_update())
        word = await session.scalar(select(Word).where(Word.id == word_id).with_for_update())
        if theme is None or word is None:
            raise InvalidResourceError("unknown theme or word")
        existing = await get_word(sessions, word_id, theme_key=key)
        if existing is not None:
            return existing
        neutral = await get_word(sessions, word_id)
        if neutral is None or any(sense.definition is None for sense in neutral.senses):
            raise InvalidResourceError("word has incomplete neutral meanings")
        instruction, data = render_prompt(
            "vocabulary/generation/prompts/generate_themed_word.jinja",
            neutral_word={
                "word": neutral.lemma,
                "senses": [
                    {
                        "pos": sense.pos.value,
                        "tier": sense.tier.value,
                        "meaning_anchor": sense.definition.content,
                    }
                    for sense in neutral.senses
                    if sense.definition is not None
                ],
            },
            theme={"voice": theme.voice, "diction": theme.diction},
            generation_parameters={"examples_per_sense": example_count},
        )
        output = await structured_llm.complete(instruction, data, ThemedWord)
        if len(output.senses) != len(neutral.senses):
            raise InvalidOutputError("themed inventory does not match neutral inventory")
        for sense, group in zip(neutral.senses, output.senses, strict=True):
            if len(group.examples) != example_count:
                raise InvalidOutputError("themed example count does not match request")
            for example in group.examples:
                marked_occurrences(example, target_sequences(neutral, sense))
            session.add(Definition(sense_id=sense.id, theme_id=theme.id, content=group.definition))
            session.add_all(
                Example(sense_id=sense.id, theme_id=theme.id, content=example)
                for example in group.examples
            )
    if cache is not None:
        cache.clear()
    return await get_word(sessions, word_id, theme_key=key, cache=cache)
