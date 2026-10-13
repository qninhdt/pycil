"""Translations reuse the exact unwrapped source text and requested language."""

import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.infrastructure.database import transaction_lock
from pycil.infrastructure.llm import render_prompt
from pycil.vocabulary.errors import InvalidResourceError
from pycil.vocabulary.models import Translation
from pycil.vocabulary.text import content_hash, strip_markup

LANGUAGE = re.compile(r"[a-z]{2}(?:-[A-Z]{2})?")


class TranslationProvider(Protocol):
    async def complete(
        self, instruction: str, data: str, schema: type[TranslationOutput]
    ) -> TranslationOutput: ...


class TranslationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=16000)

    @field_validator("content")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("translation must not be blank")
        return value


async def translate_text(
    sessions: async_sessionmaker[AsyncSession],
    structured_llm: TranslationProvider,
    content: str,
    target_language: str,
) -> str:
    if not LANGUAGE.fullmatch(target_language):
        raise InvalidResourceError("invalid translation language")
    try:
        plain = strip_markup(content)
        fingerprint = content_hash(plain)
    except ValueError as error:
        raise InvalidResourceError("invalid translation text or markup") from error
    async with sessions() as session, session.begin():
        await transaction_lock(session, f"translation:{target_language}:{fingerprint}")
        existing = await session.scalar(
            select(Translation.content).where(
                Translation.input_hash == fingerprint,
                Translation.target_language == target_language,
            )
        )
        if existing is not None:
            return existing
        translated = await structured_llm.complete(
            *render_prompt(
                "vocabulary/prompts/translate.jinja", content=plain, target_language=target_language
            ),
            TranslationOutput,
        )
        session.add(
            Translation(
                input_hash=fingerprint, target_language=target_language, content=translated.content
            )
        )
        return translated.content
