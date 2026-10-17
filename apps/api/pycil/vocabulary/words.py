"""Bounded lexical reads and canonical publication identities."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from itertools import batched
from typing import cast
from uuid import UUID

from sqlalchemy import and_, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.expression import ColumnExpressionArgument

from pycil.infrastructure.database import json_collection, transaction_lock
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.library.config import LibraryConfig
from pycil.library.scope import ScopeBudget, bounded, resolve_scopes
from pycil.library.types import SenseSourcesSummary
from pycil.study.config import StudyConfig
from pycil.study.models import UserSense
from pycil.study.progress import learning_preview
from pycil.themes.namespace import theme_scope
from pycil.utils.errors import Conflict, InvalidInput, NotFound
from pycil.utils.hashing import sha256_hex
from pycil.vocabulary import models as rows
from pycil.vocabulary.config import PreviewPolicy
from pycil.vocabulary.enums import EntryType, GenerationState, ResolutionState
from pycil.vocabulary.errors import InvalidResourceError, WordCollisionError
from pycil.vocabulary.revisions import Snapshot, capture
from pycil.vocabulary.schemas import CachedWord, Sense, Word, sense_adapter
from pycil.vocabulary.text import match_key
from pycil.vocabulary.types import MeaningInventory, SenseSummaryDict, WordAliasInsert

DEFAULT_PREVIEW_POLICY = PreviewPolicy()


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


def sense_value(data: dict[str, object]) -> Sense:
    data = dict(data)
    for name in ("patterns", "collocations"):
        items = cast(list[dict[str, str]], data.get(name) or [])
        data[name] = [item["content"] for item in items]
    relations: list[dict[str, object]] = []
    edges = cast(list[dict[str, object]], data.pop("relations", []))
    for edge in edges:
        content = cast(str | None, edge.pop("evidence"))
        fingerprint = cast(str | None, edge.pop("target_hash"))
        attempted = bool(edge.pop("attempted"))
        resolved = content is not None and sha256_hex(content) == fingerprint
        edge["resolution_state"] = (
            ResolutionState.RESOLVED
            if resolved
            else ResolutionState.UNRESOLVABLE
            if edge.get("to_sense_id") is None and attempted
            else ResolutionState.PENDING
        )
        if not resolved:
            edge["to_sense_id"] = None
        relations.append(edge)
    return sense_adapter.validate_python(data | {"relations": relations})


async def get_senses(
    sessions: async_sessionmaker[AsyncSession],
    identifiers: Sequence[int],
    *,
    theme_id: int | None = None,
    store: InMemoryStore[int, Sense] | None = None,
) -> list[Sense]:
    if theme_id is not None:
        store = None
    found: dict[int, Sense] = {}
    if store is not None:
        found = {
            identifier: cached
            for identifier in identifiers
            if (cached := store.get(identifier)) is not None
        }
    missing = list(
        dict.fromkeys(identifier for identifier in identifiers if identifier not in found)
    )
    if missing:
        async with sessions() as session:
            for batch in batched(missing, 500, strict=False):
                payload = await session.scalar(
                    select(
                        json_collection(
                            rows.Sense.__table__,
                            sense_fields(theme_id),
                            rows.Sense.id.in_(batch),
                            order_by=(rows.Sense.id,),
                        )
                    )
                )
                if isinstance(payload, list):
                    for item in cast(list[dict[str, object]], payload):
                        value = sense_value(item)
                        found[value.id] = value
                        if store is not None:
                            store.put(value.id, value)
    return [found[identifier] for identifier in identifiers if identifier in found]


async def get_word(
    sessions: async_sessionmaker[AsyncSession],
    identifier: int,
    *,
    theme_key: str | None = None,
    word_store: InMemoryStore[int, CachedWord] | None = None,
    sense_store: InMemoryStore[int, Sense] | None = None,
) -> Word | None:
    if theme_key is not None:
        word_store = None
        sense_store = None
    if word_store is not None and (cached := word_store.get(identifier)) is not None:
        senses = await get_senses(sessions, cached.sense_ids, store=sense_store)
        if len(senses) == len(cached.sense_ids):
            return Word(
                id=cached.id,
                lemma=cached.lemma,
                type=cached.type,
                generation_state=cached.generation_state,
                aliases=list(cached.aliases),
                related=list(cached.related),
                senses=senses,
            )
        word_store.discard(identifier)
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
    if sense_store is not None:
        for sense in value.senses:
            sense_store.put(sense.id, sense)
    if word_store is not None:
        word_store.put(
            value.id,
            CachedWord(
                id=value.id,
                lemma=value.lemma,
                type=value.type,
                generation_state=value.generation_state,
                aliases=tuple(value.aliases),
                related=tuple(value.related),
                sense_ids=tuple(sense.id for sense in value.senses),
            ),
        )
    return value


async def get_sense_previews(
    sessions: async_sessionmaker[AsyncSession], identifiers: Sequence[int]
) -> list[SenseSummaryDict]:
    result: dict[int, SenseSummaryDict] = {}
    async with sessions() as session:
        for batch in batched(identifiers, 500, strict=False):
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
                    .where(rows.Sense.id.in_(batch))
                )
            ).mappings()
            result.update((item["sense_id"], cast(SenseSummaryDict, dict(item))) for item in values)
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
) -> tuple[rows.Word, dict[int, Snapshot]]:
    key = match_key(lemma)
    await transaction_lock(session, "word:" + key)
    word = await session.scalar(
        select(rows.Word).where(rows.Word.match_key == key).with_for_update()
    )
    previous = await capture(session, [word.id]) if word is not None else {}
    if word is None:
        word = rows.Word(
            lemma=lemma,
            match_key=key,
            entry_type=entry_type,
            generation_state=GenerationState.PENDING,
        )
        session.add(word)
        await session.flush()
    previous.setdefault(word.id, None)
    await link_reference(session, word.id, source_id)
    if word.generation_state == GenerationState.DONE:
        return word, previous
    word.lemma, word.entry_type = lemma, entry_type
    seen: set[str] = {key}
    values: list[WordAliasInsert] = []
    for alias in aliases:
        normalized = match_key(alias)
        if normalized not in seen:
            seen.add(normalized)
            values.append({"word_id": word.id, "content": alias, "match_key": normalized})
    if values:
        await session.execute(insert(rows.WordAlias).on_conflict_do_nothing(), values)
    return word, previous


async def target_words(
    session: AsyncSession, lemmas: Sequence[str]
) -> tuple[dict[str, int], dict[int, Snapshot]]:
    unique = {match_key(lemma): lemma for lemma in lemmas}
    if not unique:
        return {}, {}
    values = [
        dict(lemma=lemma, match_key=key, generation_state=GenerationState.PENDING)
        for key, lemma in unique.items()
    ]
    created = list(
        await session.scalars(
            insert(rows.Word)
            .on_conflict_do_nothing(index_elements=[rows.Word.match_key])
            .returning(rows.Word.id),
            values,
        )
    )
    result = await session.execute(
        select(rows.Word.match_key, rows.Word.id).where(rows.Word.match_key.in_(unique))
    )
    return dict(result.all()), {identifier: None for identifier in created}


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


async def word_previews(
    session: AsyncSession,
    sessions: async_sessionmaker[AsyncSession],
    identifiers: Sequence[int],
    policy: PreviewPolicy = DEFAULT_PREVIEW_POLICY,
    *,
    sense_store: InMemoryStore[int, Sense] | None = None,
) -> list[dict[str, object]]:
    if len(identifiers) > policy.max_word_ids:
        raise InvalidInput("lexical_batch_too_large")
    words_query = select(rows.Word).where(rows.Word.id.in_(identifiers))
    words = {w.id: w for w in (await session.scalars(words_query)).all()}
    if set(words) != set(identifiers):
        raise NotFound("word_not_found")
    result_rows = list(
        (
            await session.execute(
                select(rows.Sense.id, rows.Sense.word_id)
                .where(rows.Sense.word_id.in_(identifiers))
                .order_by(rows.Sense.id)
                .limit(policy.max_word_senses + 1)
            )
        ).all()
    )
    if len(result_rows) > policy.max_word_senses:
        raise InvalidInput("lexical_batch_too_large")
    senses_page = await get_senses(sessions, [r.id for r in result_rows], store=sense_store)
    native = {s.id: s for s in senses_page}
    if set(native) != {r.id for r in result_rows}:
        raise Conflict("learning_content_changed")
    groups: dict[int, list[Sense]] = {i: [] for i in identifiers}
    for row in result_rows:
        groups[row.word_id].append(
            replace(
                native[row.id],
                examples=native[row.id].examples[: policy.inline_examples],
            )
        )
    return [
        {
            "word_id": i,
            "lemma": words[i].lemma,
            "entry_type": words[i].entry_type,
            "senses": groups[i],
        }
        for i in identifiers
    ]


async def viewer_context(
    session: AsyncSession,
    user_id: UUID,
    identifiers: Sequence[int],
    *,
    library_config: LibraryConfig,
    study_config: StudyConfig,
    policy: PreviewPolicy = DEFAULT_PREVIEW_POLICY,
    include_sources: bool = True,
    max_senses: int | None = None,
) -> dict[str, object]:
    if len(identifiers) > (max_senses or policy.max_context_senses) or len(set(identifiers)) != len(
        identifiers
    ):
        raise InvalidInput("context_too_large")
    sense_ids_query = select(rows.Sense.id).where(rows.Sense.id.in_(identifiers))
    found = set((await session.scalars(sense_ids_query)).all())
    if found != set(identifiers):
        raise NotFound("sense_not_found")
    budget = ScopeBudget(user_id)
    async with bounded(session, library_config, budget):
        scope = (
            next(
                iter(
                    (
                        await resolve_scopes(
                            session,
                            [None],
                            user_id,
                            library_config,
                            budget=budget,
                        )
                    ).values()
                )
            )
            if include_sources
            else None
        )
        memories = {
            m.sense_id: m
            for m in (
                await session.scalars(
                    select(UserSense).where(
                        UserSense.user_id == user_id, UserSense.sense_id.in_(identifiers)
                    )
                )
            ).all()
        }
        from pycil.library.senses import source_batch

        membership: dict[int, SenseSourcesSummary] = (
            await source_batch(
                session,
                scope.decks,
                identifiers,
                user_id,
                policy.inline_sources,
            )
            if scope
            else {i: {"decks": [], "count": 0} for i in identifiers}
        )
        now = datetime.now(UTC)
        senses = [
            {
                "sense_id": identifier,
                "learning": learning_preview(memories.get(identifier), now, user_id, study_config),
                "decks": membership[identifier]["decks"],
                "deck_count": membership[identifier]["count"],
                "decks_has_more": int(membership[identifier]["count"]) > policy.inline_sources,
            }
            for identifier in identifiers
        ]
        studied = len(memories)
        due = sum(m.due_at <= now for m in memories.values())
        return {
            "as_of": now,
            "senses": senses,
            "total": len(identifiers),
            "studied": studied,
            "new": len(identifiers) - studied,
            "due": due,
            "not_due": studied - due,
        }


async def word_context(
    session: AsyncSession,
    user_id: UUID,
    word_id: int,
    *,
    library_config: LibraryConfig,
    study_config: StudyConfig,
    policy: PreviewPolicy = DEFAULT_PREVIEW_POLICY,
) -> dict[str, object]:
    if await session.get(rows.Word, word_id) is None:
        raise NotFound("word_not_found")
    identifiers = list(
        (
            await session.scalars(
                select(rows.Sense.id)
                .where(rows.Sense.word_id == word_id)
                .order_by(rows.Sense.id)
                .limit(policy.max_context_senses + 1)
            )
        ).all()
    )
    return await viewer_context(
        session,
        user_id,
        identifiers,
        library_config=library_config,
        study_config=study_config,
        policy=policy,
    )
