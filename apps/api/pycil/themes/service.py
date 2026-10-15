"""Theme identity lifecycle; existing generated namespaces survive descriptor edits."""

from typing import Protocol, cast

from pydantic import BaseModel
from sqlalchemy import CursorResult, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.infrastructure.llm import render_prompt
from pycil.themes.errors import InvalidThemeError
from pycil.themes.models import Theme as ThemeRow
from pycil.themes.namespace import normalize_key
from pycil.themes.schemas import Theme, ThemeParts


class StructuredLLMProtocol(Protocol):
    async def complete[T: BaseModel](self, instruction: str, data: str, schema: type[T]) -> T: ...


class CacheProtocol(Protocol):
    def clear(self) -> None: ...


async def get_theme(
    sessions: async_sessionmaker[AsyncSession],
    key: str,
) -> Theme | None:
    async with sessions() as session:
        row = await session.scalar(select(ThemeRow).where(ThemeRow.key == normalize_key(key)))
        return Theme.model_validate(row) if row is not None else None


async def create_theme(
    sessions: async_sessionmaker[AsyncSession],
    structured_llm: StructuredLLMProtocol,
    key: str,
    name: str,
    concept: str,
) -> Theme:
    norm_key = normalize_key(key)
    if not name.strip() or len(name) > 255:
        raise InvalidThemeError("invalid theme name")
    if not concept.strip() or len(concept) > 4000:
        raise InvalidThemeError("invalid theme concept")
    if await get_theme(sessions, norm_key) is not None:
        raise InvalidThemeError("theme key already exists")
    parts = await structured_llm.complete(
        *render_prompt("themes/prompts/generate_theme.jinja", theme_prompt=concept), ThemeParts
    )
    try:
        async with sessions() as session, session.begin():
            row = ThemeRow(key=norm_key, name=name, **parts.model_dump())
            session.add(row)
            await session.flush()
            return Theme.model_validate(row)
    except IntegrityError as error:
        raise InvalidThemeError("theme key already exists") from error


async def update_theme(
    sessions: async_sessionmaker[AsyncSession],
    key: str,
    *,
    name: str | None = None,
    voice: str | None = None,
    diction: str | None = None,
) -> Theme:
    changes: dict[str, str] = {
        field: value
        for field, value in (("name", name), ("voice", voice), ("diction", diction))
        if value is not None
    }
    for field, value in changes.items():
        maximum = 255 if field == "name" else 1000
        if not value.strip() or len(value) > maximum:
            raise InvalidThemeError("invalid theme field")
    async with sessions() as session, session.begin():
        row = await session.scalar(
            select(ThemeRow).where(ThemeRow.key == normalize_key(key)).with_for_update()
        )
        if row is None:
            raise InvalidThemeError("unknown theme")
        for field, value in changes.items():
            setattr(row, field, value)
        return Theme.model_validate(row)


async def delete_theme(
    sessions: async_sessionmaker[AsyncSession],
    key: str,
    *,
    word_cache: CacheProtocol | None = None,
    sense_cache: CacheProtocol | None = None,
    artifact_cache: CacheProtocol | None = None,
) -> bool:
    async with sessions() as session, session.begin():
        result = await session.execute(delete(ThemeRow).where(ThemeRow.key == normalize_key(key)))
        cursor_result = cast(CursorResult[tuple[()]], result)
        removed = bool(cursor_result.rowcount)
    if removed:
        for cache in (word_cache, sense_cache, artifact_cache):
            if cache is not None:
                cache.clear()
    return removed
