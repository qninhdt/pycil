"""Bounded lexical reads and canonical publication identities."""

from collections.abc import Sequence
from hashlib import sha256
from typing import Any, cast

from sqlalchemy import and_, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.expression import ColumnExpressionArgument

from pycil.infrastructure.database import json_collection, transaction_lock
from pycil.themes.namespace import theme_scope
from pycil.vocabulary import models as rows
from pycil.vocabulary.cache import ContentCache
from pycil.vocabulary.enums import EntryType, GenerationState, ResolutionState
from pycil.vocabulary.errors import InvalidResourceError, WordCollisionError
from pycil.vocabulary.schemas import Sense, Word
from pycil.vocabulary.text import match_key
from pycil.vocabulary.types import MeaningInventory, SensePreview


def sense_fields(
    theme_id: ColumnExpressionArgument[int] | int | None, *, relations: bool = True
) -> dict[str, ColumnElement[object]]:
    source = rows.Sense.__table__
    fields: dict[str, ColumnElement[object]] = dict(source.c.items())
    definition = rows.Definition.__table__
    fields["definition"] = (
        select(
            func.jsonb_build_object(
                "id",
                definition.c.id,
                "content",
                definition.c.content,
                "theme_id",
                definition.c.theme_id,
            )
        )
        .where(definition.c.sense_id == source.c.id, definition.c.theme_id == theme_id)
        .correlate(source)
        .scalar_subquery()
    )
    for name, model, columns in (
        ("examples", rows.Example, ("id", "content", "theme_id")),
        ("forms", rows.SenseForm, ("surface", "inf")),
        ("patterns", rows.SensePattern, ("content",)),
        ("collocations", rows.Collocation, ("content",)),
    ):
        table = model.__table__
        conditions = [table.c.sense_id == source.c.id]
        if name == "examples":
            conditions.append(table.c.theme_id == theme_id)
        fields[name] = json_collection(
            table,
            {name: table.c[name] for name in columns},
            *conditions,
            order_by=(table.c.id,),
            correlate=(source,),
        )
    if not relations:
        return fields
    edge = rows.SenseRelation.__table__
    target = rows.Word.__table__.alias("relation_target")
    evidence = rows.Definition.__table__.alias("relation_definition")
    content = (
        select(evidence.c.content)
        .where(evidence.c.sense_id == edge.c.to_sense_id, evidence.c.theme_id.is_(None))
        .correlate(edge)
        .scalar_subquery()
    )
    fields["relations"] = json_collection(
        edge.join(target, edge.c.to_word_id == target.c.id),
        dict(
            rel_type=edge.c.rel_type,
            to_word_id=target.c.id,
            to_word_lemma=target.c.lemma,
            to_sense_id=edge.c.to_sense_id,
            target_hash=edge.c.target_hash,
            attempted=edge.c.resolve_attempted_at,
            evidence=content,
        ),
        edge.c.from_sense_id == source.c.id,
        order_by=(edge.c.id,),
        correlate=(source,),
    )
    return fields


def sense_value(data: dict[str, Any]) -> Sense:
    data = dict(data)
    for name in ("patterns", "collocations"):
        data[name] = [item["content"] for item in data[name]]
    relations: list[dict[str, Any]] = []
    for edge in data.pop("relations", []):
        content = edge.pop("evidence")
        fingerprint = edge.pop("target_hash")
        attempted = edge.pop("attempted")
        resolved = content is not None and sha256(content.encode()).hexdigest() == fingerprint
        edge["resolution_state"] = (
            ResolutionState.RESOLVED
            if resolved
            else ResolutionState.UNRESOLVABLE
            if edge["to_sense_id"] is None and attempted
            else ResolutionState.PENDING
        )
        if not resolved:
            edge["to_sense_id"] = None
        relations.append(edge)
    return Sense.model_validate(data | {"relations": relations})


async def get_senses(
    sessions: async_sessionmaker[AsyncSession],
    identifiers: Sequence[int],
    *,
    theme_id: int | None = None,
    cache: ContentCache | None = None,
) -> list[Sense]:
    found: dict[int, Sense] = {}
    if cache is not None:
        found = {
            identifier: cached
            for identifier in identifiers
            if (cached := cache.get(("sense", identifier, theme_id), Sense)) is not None
        }
    missing = list(
        dict.fromkeys(identifier for identifier in identifiers if identifier not in found)
    )
    async with sessions() as session:
        for offset in range(0, len(missing), 500):
            payload = await session.scalar(
                select(
                    json_collection(
                        rows.Sense.__table__,
                        sense_fields(theme_id),
                        rows.Sense.id.in_(missing[offset : offset + 500]),
                        order_by=(rows.Sense.id,),
                    )
                )
            )
            if isinstance(payload, list):
                for item in cast(list[dict[str, Any]], payload):
                    value = sense_value(item)
                    found[value.id] = value
                    if cache is not None:
                        cache.put(("sense", value.id, theme_id), value)
    return [found[identifier] for identifier in identifiers if identifier in found]


async def get_word(
    sessions: async_sessionmaker[AsyncSession],
    identifier: int | str,
    *,
    theme_key: str | None = None,
    cache: ContentCache | None = None,
) -> Word | None:
    key = "word", identifier, theme_key
    if cache is not None and (value := cache.get(key, Word)) is not None:
        return value
    theme_id, valid = theme_scope(theme_key=theme_key)
    source = rows.Word.__table__
    edge = rows.WordRelation.__table__
    target = source.alias("word_relation_target")
    fields: dict[str, ColumnElement[object]] = {
        name: source.c[name] for name in ("id", "lemma", "entry_type", "generation_state")
    }
    fields["aliases"] = json_collection(
        rows.WordAlias.__table__,
        {"content": rows.WordAlias.content},
        rows.WordAlias.word_id == identifier,
        order_by=(rows.WordAlias.id,),
    )
    fields["senses"] = json_collection(
        rows.Sense.__table__,
        sense_fields(theme_id),
        rows.Sense.word_id == source.c.id,
        order_by=(rows.Sense.id,),
        correlate=(source,),
    )
    fields["related"] = json_collection(
        edge.join(target, edge.c.to_word_id == target.c.id),
        dict(rel_type=edge.c.rel_type, to_word_id=target.c.id, to_word_lemma=target.c.lemma),
        edge.c.from_word_id == source.c.id,
        order_by=(edge.c.id,),
        correlate=(source,),
    )
    pairs = [part for name, val in fields.items() for part in (literal(name), val)]
    payload = (
        select(func.jsonb_build_object(*pairs))
        .where(
            rows.Word.id == identifier, rows.Word.generation_state == GenerationState.DONE, valid
        )
        .scalar_subquery()
    )
    async with sessions() as session:
        theme_valid, data = (await session.execute(select(valid, payload))).one()
    if not theme_valid:
        raise InvalidResourceError("unknown theme")
    if data is None or not data["senses"]:
        return None
    data["senses"] = [sense_value(item) for item in data["senses"]]
    if theme_key is not None and any(
        sense.definition is None or not sense.examples for sense in data["senses"]
    ):
        return None
    data["aliases"] = [item["content"] for item in data["aliases"]]
    data["type"] = data.pop("entry_type")
    value = Word.model_validate(data)
    if cache is not None:
        cache.put(key, value)
        if theme_key is None:
            for sense in value.senses:
                cache.put(("sense", sense.id, None), sense)
    return value


async def get_sense_previews(
    sessions: async_sessionmaker[AsyncSession], identifiers: Sequence[int]
) -> list[SensePreview]:
    result: dict[int, SensePreview] = {}
    async with sessions() as session:
        for offset in range(0, len(identifiers), 500):
            values = (
                await session.execute(
                    select(
                        rows.Sense.id.label("sense_id"),
                        rows.Sense.word_id,
                        rows.Word.lemma,
                        rows.Word.entry_type,
                        rows.Sense.pos,
                        rows.Sense.tier,
                        rows.Sense.cefr_level,
                        rows.Sense.register,
                        rows.Sense.ipa_uk,
                        rows.Sense.ipa_us,
                        rows.Definition.content.label("definition"),
                    )
                    .join(rows.Word, rows.Word.id == rows.Sense.word_id)
                    .outerjoin(
                        rows.Definition,
                        and_(
                            rows.Definition.sense_id == rows.Sense.id,
                            rows.Definition.theme_id.is_(None),
                        ),
                    )
                    .where(rows.Sense.id.in_(identifiers[offset : offset + 500]))
                )
            ).mappings()
            result.update((item["sense_id"], cast(SensePreview, dict(item))) for item in values)
    return [result[identifier] for identifier in identifiers if identifier in result]


async def consumed_word(session: AsyncSession, source_id: int) -> int | None:
    return await session.scalar(
        select(rows.Word.id)
        .join(rows.WordReference)
        .where(
            rows.WordReference.source_id == source_id,
            rows.Word.generation_state == GenerationState.DONE,
        )
    )


async def link_reference(session: AsyncSession, word_id: int, source_id: int) -> None:
    existing = await session.scalar(
        select(rows.WordReference.word_id).where(rows.WordReference.source_id == source_id)
    )
    if existing is not None and existing != word_id:
        raise WordCollisionError("reference already belongs to a different word")
    if existing is None:
        session.add(rows.WordReference(word_id=word_id, source_id=source_id))
        await session.flush()


async def publish_identity(
    session: AsyncSession,
    source_id: int,
    lemma: str,
    entry_type: EntryType | None,
    aliases: Sequence[str],
) -> rows.Word:
    key = match_key(lemma)
    await transaction_lock(session, "word:" + key)
    word = await session.scalar(
        select(rows.Word).where(rows.Word.match_key == key).with_for_update()
    )
    if word is None:
        word = rows.Word(
            lemma=lemma,
            match_key=key,
            entry_type=entry_type,
            generation_state=GenerationState.PENDING,
        )
        session.add(word)
        await session.flush()
    await link_reference(session, word.id, source_id)
    if word.generation_state == GenerationState.DONE:
        return word
    word.lemma, word.entry_type = lemma, entry_type
    seen: set[str] = {key}
    values: list[dict[str, Any]] = []
    for alias in aliases:
        normalized = match_key(alias)
        if normalized not in seen:
            seen.add(normalized)
            values.append(dict(word_id=word.id, content=alias, match_key=normalized))
    if values:
        await session.execute(insert(rows.WordAlias).on_conflict_do_nothing(), values)
    return word


async def target_words(session: AsyncSession, lemmas: Sequence[str]) -> dict[str, int]:
    unique = {match_key(lemma): lemma for lemma in lemmas}
    if not unique:
        return {}
    values = [
        dict(lemma=lemma, match_key=key, generation_state=GenerationState.PENDING)
        for key, lemma in unique.items()
    ]
    await session.execute(
        insert(rows.Word).on_conflict_do_nothing(index_elements=[rows.Word.match_key]), values
    )
    result = await session.execute(
        select(rows.Word.match_key, rows.Word.id).where(rows.Word.match_key.in_(unique))
    )
    return dict(result.all())


async def meaning_inventory(
    sessions: async_sessionmaker[AsyncSession],
    *,
    word_id: int | None = None,
    sense_id: int | None = None,
) -> MeaningInventory | None:
    if (word_id is None) == (sense_id is None):
        raise ValueError("select one word or its owning sense")
    identifier = (
        word_id
        if word_id is not None
        else select(rows.Sense.word_id).where(rows.Sense.id == sense_id).scalar_subquery()
    )
    source = rows.Sense.__table__.outerjoin(
        rows.Definition.__table__,
        and_(rows.Definition.sense_id == rows.Sense.id, rows.Definition.theme_id.is_(None)),
    )
    senses = json_collection(
        source,
        dict(id=rows.Sense.id, pos=rows.Sense.pos, definition=rows.Definition.content),
        rows.Sense.word_id == rows.Word.id,
        order_by=(rows.Sense.id,),
        correlate=(rows.Word.__table__,),
    )
    async with sessions() as session:
        value = (
            (
                await session.execute(
                    select(rows.Word.id, rows.Word.lemma, senses.label("senses")).where(
                        rows.Word.id == identifier,
                        rows.Word.generation_state == GenerationState.DONE,
                    )
                )
            )
            .mappings()
            .first()
        )
    if value is not None and any(item["definition"] is None for item in value["senses"]):
        raise InvalidResourceError("word has incomplete neutral meanings")
    return cast(MeaningInventory, dict(value)) if value is not None else None
