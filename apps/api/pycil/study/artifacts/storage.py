"""Append-only exercise banks and bounded sampling by dense indexed positions."""

import random
from collections.abc import Sequence
from itertools import batched
from typing import cast

import orjson
from sqlalchemy import Integer, column, delete, func, literal, or_, select, tuple_, values
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.infrastructure.content_revisions import capture, lock_owners, publish
from pycil.infrastructure.database import json_collection
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.study.artifacts.schemas import ARTIFACT_SCHEMAS, Artifact
from pycil.study.enums import SINGLETON_ARTIFACT_TYPES, QuestionArtifactType
from pycil.study.errors import QuestionArtifactBankChangedError
from pycil.study.models import QuestionArtifact
from pycil.study.types import ThemeContext
from pycil.themes.models import Theme
from pycil.themes.namespace import theme_scope
from pycil.utils.hashing import sha256_hex
from pycil.vocabulary.enums import EntryType, GenerationState
from pycil.vocabulary.errors import InvalidResourceError
from pycil.vocabulary.models import Sense, Word, WordAlias
from pycil.vocabulary.schemas import Sense as SenseSchema
from pycil.vocabulary.schemas import Word as WordValue
from pycil.vocabulary.text import answer_key, strip_markup
from pycil.vocabulary.words import sense_fields, sense_value

randomness = random.SystemRandom()


def artifact_value(row: QuestionArtifact) -> Artifact:
    payload = ARTIFACT_SCHEMAS[row.artifact_type].model_validate_json(row.payload).model_dump()
    return Artifact(
        id=row.id,
        sense_id=row.sense_id,
        theme_id=row.theme_id,
        artifact_type=row.artifact_type,
        payload=payload,
    )


async def get_many(
    sessions: async_sessionmaker[AsyncSession],
    identifiers: Sequence[int],
    *,
    store: InMemoryStore[int, Artifact] | None = None,
) -> list[Artifact]:
    found: dict[int, Artifact] = {}
    if store is not None:
        found = {
            identifier: value
            for identifier in identifiers
            if (value := store.get(identifier)) is not None
        }
    missing = list(
        dict.fromkeys(identifier for identifier in identifiers if identifier not in found)
    )
    async with sessions() as session:
        for batch in batched(missing, 500, strict=False):
            for row in await session.scalars(
                select(QuestionArtifact).where(QuestionArtifact.id.in_(batch))
            ):
                value = artifact_value(row)
                found[value.id] = value
                if store is not None:
                    store.put(value.id, value)
    return [found[identifier] for identifier in dict.fromkeys(identifiers) if identifier in found]


def _merge_singleton(
    existing: dict[str, object],
    increment: dict[str, object],
    kind: QuestionArtifactType,
) -> dict[str, object]:
    existing_corrects = cast(list[object], existing["corrects"])
    existing_distractors = cast(list[object], existing["distractors"])
    payload: dict[str, list[object]] = {
        "corrects": list(existing_corrects),
        "distractors": list(existing_distractors),
    }
    paired = kind is QuestionArtifactType.WORD_DEFINITION

    def key(text: str) -> str:
        return answer_key(strip_markup(text))

    texts = {key(cast(str, text)) for text in payload["corrects"]}
    texts.update(
        key(cast(dict[str, str], value)["definition"] if paired else cast(str, value))
        for value in payload["distractors"]
    )
    words: set[str] = (
        {key(cast(dict[str, str], value)["word"]) for value in payload["distractors"]}
        if paired
        else set[str]()
    )
    for name in ("corrects", "distractors"):
        for value in cast(list[object], increment[name]):
            pair = paired and name == "distractors"
            identity = key(cast(dict[str, str], value)["definition"] if pair else cast(str, value))
            word = key(cast(dict[str, str], value)["word"]) if pair else None
            if identity not in texts and (word is None or word not in words):
                payload[name].append(value)
                texts.add(identity)
                if pair and word is not None:
                    words.add(word)
    if not payload["corrects"] or not payload["distractors"]:
        raise InvalidResourceError("singleton bank needs both answer sets")
    return cast(dict[str, object], payload)


async def append(
    sessions: async_sessionmaker[AsyncSession],
    artifacts: Sequence[Artifact],
    *,
    store: InMemoryStore[int, Artifact] | None = None,
) -> list[Artifact]:
    if not artifacts:
        return []
    prepared: list[tuple[Artifact, dict[str, object], str, str]] = []
    for artifact in artifacts:
        kind = artifact.artifact_type
        payload = ARTIFACT_SCHEMAS[kind].model_validate(artifact.payload).model_dump()
        encoded = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode()
        prepared.append((artifact, payload, encoded, sha256_hex(encoded)))
    saved: dict[tuple[int, int | None, QuestionArtifactType, str | None], QuestionArtifact] = {}
    existing: dict[tuple[int, int | None, QuestionArtifactType, str | None], QuestionArtifact] = {}
    async with sessions() as session, session.begin():
        ids = sorted({artifact.sense_id for artifact in artifacts})
        # Theme -> word -> artifact is the common cascade/mutation lock order.
        await lock_owners(
            session,
            [
                ("theme", identifier)
                for identifier in sorted({a.theme_id for a in artifacts if a.theme_id is not None})
            ],
        )
        owners = list(
            await session.scalars(select(Sense.word_id).where(Sense.id.in_(ids)).distinct())
        )
        await lock_owners(session, [("word", identifier) for identifier in owners])
        found = set(
            await session.scalars(
                select(Sense.id).where(Sense.id.in_(ids)).order_by(Sense.id).with_for_update()
            )
        )
        if found != set(ids):
            raise InvalidResourceError("artifact sense was removed")
        for batch in batched(prepared, 500, strict=False):
            scopes = {
                (artifact.sense_id, artifact.theme_id or 0, artifact.artifact_type)
                for artifact, *_rest in batch
            }
            rows = await session.scalars(
                select(QuestionArtifact).where(
                    tuple_(
                        QuestionArtifact.sense_id,
                        func.coalesce(QuestionArtifact.theme_id, 0),
                        QuestionArtifact.artifact_type,
                    ).in_(scopes),
                    or_(
                        QuestionArtifact.artifact_type.in_(SINGLETON_ARTIFACT_TYPES),
                        QuestionArtifact.payload_hash.in_([item[3] for item in batch]),
                    ),
                )
            )
            for row in rows:
                fingerprint = (
                    None if row.artifact_type in SINGLETON_ARTIFACT_TYPES else row.payload_hash
                )
                existing[row.sense_id, row.theme_id, row.artifact_type, fingerprint] = row
        before = await capture(
            session, [("question_artifact", row.id) for row in existing.values()]
        )
        for artifact, payload, encoded, fingerprint in prepared:
            kind = artifact.artifact_type
            singleton = kind in SINGLETON_ARTIFACT_TYPES
            key = (artifact.sense_id, artifact.theme_id, kind, None if singleton else fingerprint)
            row = existing.get(key)
            if singleton:
                current: dict[str, object] = (
                    cast(dict[str, object], orjson.loads(row.payload))
                    if row
                    else {"corrects": [], "distractors": []}
                )
                payload = _merge_singleton(current, payload, kind)
                encoded = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode()
                fingerprint = sha256_hex(encoded)
            elif row is not None:
                continue
            if row is None:
                row = QuestionArtifact(
                    sense_id=artifact.sense_id,
                    theme_id=artifact.theme_id,
                    artifact_type=kind,
                    payload=encoded,
                    payload_hash=fingerprint,
                )
                session.add(row)
                existing[key] = row
            else:
                row.payload, row.payload_hash = encoded, fingerprint
            saved[key] = row
        await session.flush()
        for row in saved.values():
            before.setdefault(("question_artifact", row.id), None)
        await publish(session, before)
        result = [artifact_value(row) for row in saved.values()]
    if store is not None:
        store.clear()
    return result


async def remove(
    sessions: async_sessionmaker[AsyncSession],
    identifier: int,
    *,
    store: InMemoryStore[int, Artifact] | None = None,
) -> int | None:
    async with sessions() as session, session.begin():
        scope = (
            await session.execute(
                select(QuestionArtifact.sense_id, QuestionArtifact.theme_id, Sense.word_id)
                .join(Sense, Sense.id == QuestionArtifact.sense_id)
                .where(QuestionArtifact.id == identifier)
            )
        ).one_or_none()
        if scope is None:
            return None
        if scope.theme_id is not None:
            await lock_owners(session, [("theme", scope.theme_id)])
        await lock_owners(session, [("word", scope.word_id)])
        await session.execute(select(Sense.id).where(Sense.id == scope.sense_id).with_for_update())
        # The dense-position trigger can move another artifact in the same bank.
        identifiers = list(
            await session.scalars(
                select(QuestionArtifact.id).where(
                    QuestionArtifact.sense_id == scope.sense_id,
                    QuestionArtifact.theme_id == scope.theme_id,
                )
            )
        )
        before = await capture(session, [("question_artifact", value) for value in identifiers])
        await session.execute(delete(QuestionArtifact).where(QuestionArtifact.id == identifier))
        revision = await publish(session, before)
    if store is not None:
        store.clear()
    return revision


async def bank_sizes(
    sessions: async_sessionmaker[AsyncSession],
    requests: Sequence[tuple[int, QuestionArtifactType]],
    *,
    theme_key: str | None = None,
) -> dict[tuple[int, QuestionArtifactType], int]:
    identifier, valid = theme_scope(theme_key=theme_key)
    result: dict[tuple[int, QuestionArtifactType], int] = {}
    async with sessions() as session:
        if not await session.scalar(select(valid)):
            raise InvalidResourceError("unknown theme")
        for batch in batched(requests, 500, strict=False):
            banks = (
                values(
                    column("sense_id", Integer), column("kind", QuestionArtifact.artifact_type.type)
                )
                .data(batch)
                .cte("requested_banks")
            )
            last = (
                select(QuestionArtifact.type_position)
                .where(
                    QuestionArtifact.sense_id == banks.c.sense_id,
                    QuestionArtifact.artifact_type == banks.c.kind,
                    QuestionArtifact.theme_id == identifier,
                )
                .order_by(QuestionArtifact.type_position.desc())
                .limit(1)
                .correlate(banks)
                .scalar_subquery()
            )
            rows = (await session.execute(select(banks.c.sense_id, banks.c.kind, last))).all()
            for r in rows:
                result[int(r[0]), QuestionArtifactType(r[1])] = int(r[2] or 0)
    return result


async def retrieve_many(
    sessions: async_sessionmaker[AsyncSession],
    requests: Sequence[tuple[int, QuestionArtifactType, int]],
    *,
    theme_key: str | None = None,
    store: InMemoryStore[int, Artifact] | None = None,
) -> list[Artifact]:
    pairs = [(sense_id, kind) for sense_id, kind, _quantity in requests]
    if len(set(pairs)) != len(pairs) or any(
        type(quantity) is not int or quantity < 1 for _id, _kind, quantity in requests
    ):
        raise ValueError("invalid or repeated bank request")
    sizes = await bank_sizes(sessions, pairs, theme_key=theme_key)
    slots: list[tuple[int, QuestionArtifactType, int]] = []
    for sense_id, kind, quantity in requests:
        target_qty = 1 if kind in SINGLETON_ARTIFACT_TYPES else quantity
        size = sizes[sense_id, kind]
        if size < target_qty:
            raise QuestionArtifactBankChangedError("bank cannot satisfy the request")
        slots.extend(
            (sense_id, kind, position)
            for position in randomness.sample(range(1, size + 1), target_qty)
        )
    identifier, _valid = theme_scope(theme_key=theme_key)
    ids: list[int] = []
    async with sessions() as session:
        for batch in batched(slots, 500, strict=False):
            ids.extend(
                await session.scalars(
                    select(QuestionArtifact.id).where(
                        QuestionArtifact.theme_id == identifier,
                        tuple_(
                            QuestionArtifact.sense_id,
                            QuestionArtifact.artifact_type,
                            QuestionArtifact.type_position,
                        ).in_(batch),
                    )
                )
            )
    artifacts = await get_many(sessions, ids, store=store)
    if len(artifacts) != len(slots):
        raise QuestionArtifactBankChangedError("bank changed during sampling")
    return artifacts


async def generation_context(
    sessions: async_sessionmaker[AsyncSession],
    sense_id: int,
    *,
    theme_key: str | None = None,
) -> tuple[WordValue, SenseSchema, ThemeContext | None]:
    identifier, valid = theme_scope(theme_key=theme_key)
    fields = sense_fields(identifier, relations=False)
    sense = func.jsonb_build_object(
        *[part for key, value in fields.items() for part in (literal(key), value)]
    )
    aliases = json_collection(
        WordAlias.__table__,
        {"content": WordAlias.content},
        WordAlias.word_id == Word.id,
        order_by=(WordAlias.id,),
        correlate=(Word.__table__,),
    )
    theme = (
        select(
            func.jsonb_build_object("id", Theme.id, "voice", Theme.voice, "diction", Theme.diction)
        )
        .where(Theme.id == identifier)
        .scalar_subquery()
        if theme_key is not None
        else literal(None)
    )
    async with sessions() as session:
        if not await session.scalar(select(valid)):
            raise InvalidResourceError("unknown theme")
        value = (
            await session.execute(
                select(Word.id, Word.lemma, Word.entry_type, aliases, sense, theme)
                .join(Sense, Sense.word_id == Word.id)
                .where(Sense.id == sense_id, Word.generation_state == GenerationState.DONE)
            )
        ).one_or_none()
    if value is None:
        raise InvalidResourceError("unpublished or removed sense")
    word_id = int(value[0])
    lemma = str(value[1])
    entry_type = cast(EntryType, value[2])
    alias_rows = cast(list[dict[str, str]], value[3])
    payload = cast(dict[str, object], value[4])
    theme_data = cast(ThemeContext | None, value[5])

    sense_obj = sense_value(payload)
    if sense_obj.definition is None or theme_key is not None and not sense_obj.examples:
        raise InvalidResourceError("sense is unavailable in the selected namespace")
    return (
        WordValue(
            id=word_id,
            lemma=lemma,
            type=entry_type,
            generation_state=GenerationState.DONE,
            aliases=[item["content"] for item in alias_rows],
            senses=[sense_obj],
        ),
        sense_obj,
        theme_data,
    )
