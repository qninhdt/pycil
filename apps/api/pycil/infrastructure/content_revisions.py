"""Canonical content snapshots, transactional JSON Patch history and replay."""

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import Enum
from time import perf_counter
from typing import Any, Literal, cast

import jsonpatch
import orjson
from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Sequence, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, validates

from pycil.infrastructure.database import Base, transaction_lock
from pycil.infrastructure.observability import get_logger

logger = get_logger(__name__)

EntityType = Literal["word", "question_artifact", "theme"]
type EntityKey = tuple[EntityType, int]
type Snapshot = dict[str, Any] | None
GRAPH_KEY = "pycil:content-revisions:word-graph"
PUBLICATION_KEY = "pycil:content-revisions:publication"
ENTITY_ORDER = {"theme": 0, "word": 1, "question_artifact": 2}


class ContentRevision(Base):
    __tablename__ = "content_revisions"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('word', 'question_artifact', 'theme')", name="entity_type"
        ),
        CheckConstraint("entity_id > 0", name="positive_entity_id"),
        CheckConstraint(
            "jsonb_typeof(op) = 'array' AND jsonb_array_length(op) > 0", name="patch_array"
        ),
        Index("ix_content_revisions_entity", "entity_type", "entity_id", "id"),
    )
    id: Mapped[int] = mapped_column(
        BigInteger, Sequence("content_revision_id_seq", cache=1), primary_key=True
    )
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[int] = mapped_column(BigInteger)
    op: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    @validates("op")
    def validate_patch(self, key: str, patch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(patch, list) or not patch:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("A nonempty JSON Patch array is required")
        for operation in patch:
            if not isinstance(operation, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise ValueError("Patch operations must be objects")
            action = operation.get("op")
            path = operation.get("path")
            if action not in {"add", "remove", "replace", "move", "copy", "test"}:
                raise ValueError("Unknown patch operation")
            if not isinstance(path, str) or (path and not path.startswith("/")):
                raise ValueError("Invalid JSON Pointer path")
            if action in {"add", "replace", "test"} and "value" not in operation:
                raise ValueError("Patch value is required")
            if action in {"move", "copy"}:
                source = operation.get("from")
                if not isinstance(source, str) or (source and not source.startswith("/")):
                    raise ValueError("Patch source is required")
        jsonpatch.JsonPatch(patch)
        return patch


def _values(row: Mapping[str, Any] | RowMapping, exclude: Iterable[str] = ()) -> dict[str, Any]:
    return {
        str(k): v.value if isinstance(v, Enum) else v
        for k, v in row.items()
        if str(k) not in exclude
    }


async def serialize(session: AsyncSession, kind: EntityType, identifier: int) -> Snapshot:
    from pycil.study.models import QuestionArtifact
    from pycil.themes.models import Theme
    from pycil.vocabulary import models as v

    if kind not in ENTITY_ORDER or type(identifier) is not int or identifier <= 0:
        raise ValueError("Invalid content identity")
    model = {"word": v.Word, "question_artifact": QuestionArtifact, "theme": Theme}[kind]
    row = (
        (await session.execute(select(model.__table__).where(model.id == identifier)))
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    if kind == "theme":
        return _values(row)
    if kind == "question_artifact":
        value = _values(row, ("payload_hash",))
        value["payload"] = orjson.loads(value["payload"])
        return value
    value = _values(row, ("match_key", "generation_state"))
    senses = (
        (
            await session.execute(
                select(v.Sense.__table__).where(v.Sense.word_id == identifier).order_by(v.Sense.id)
            )
        )
        .mappings()
        .all()
    )
    value["senses"] = [_values(s) for s in senses]
    sense_ids = [s["id"] for s in senses]
    for name, child, condition, excluded in (
        ("aliases", v.WordAlias, v.WordAlias.word_id == identifier, ("match_key",)),
        ("reference_links", v.WordReference, v.WordReference.word_id == identifier, ()),
        ("word_relations", v.WordRelation, v.WordRelation.from_word_id == identifier, ()),
        ("definitions", v.Definition, v.Definition.sense_id.in_(sense_ids), ()),
        ("examples", v.Example, v.Example.sense_id.in_(sense_ids), ()),
        ("forms", v.SenseForm, v.SenseForm.sense_id.in_(sense_ids), ("match_key", "head_key")),
        ("patterns", v.SensePattern, v.SensePattern.sense_id.in_(sense_ids), ("head_key",)),
        ("collocations", v.Collocation, v.Collocation.sense_id.in_(sense_ids), ()),
        ("sense_references", v.SenseReference, v.SenseReference.sense_id.in_(sense_ids), ()),
        (
            "sense_relations",
            v.SenseRelation,
            v.SenseRelation.from_sense_id.in_(sense_ids),
            ("target_hash", "resolve_attempted_at"),
        ),
    ):
        children = (
            (await session.execute(select(child.__table__).where(condition).order_by(child.id)))
            .mappings()
            .all()
        )
        value[name] = [_values(item, excluded) for item in children]
    return value


async def lock_owners(session: AsyncSession, keys: Iterable[EntityKey]) -> list[EntityKey]:
    """Lock owners in one order before reading or modifying their child content."""
    keys = sorted(set(keys), key=lambda key: (ENTITY_ORDER[key[0]], key[1]))
    from pycil.study.models import QuestionArtifact
    from pycil.themes.models import Theme
    from pycil.vocabulary.models import Word

    owners = {"word": Word, "theme": Theme, "question_artifact": QuestionArtifact}
    for kind, identifier in keys:
        model = owners[kind]
        await session.execute(select(model.id).where(model.id == identifier).with_for_update())
    return keys


async def capture(session: AsyncSession, keys: Iterable[EntityKey]) -> dict[EntityKey, Snapshot]:
    return {key: await serialize(session, *key) for key in await lock_owners(session, keys)}


async def publish(session: AsyncSession, before: Mapping[EntityKey, Snapshot]) -> int | None:
    """Allocate IDs last, keeping the shared publication lock until caller commit."""
    await session.flush()
    pending: list[ContentRevision] = []
    for (kind, identifier), previous in sorted(before.items()):
        current = await serialize(session, kind, identifier)
        if current == previous:
            continue
        if previous is None:
            patch = [{"op": "add", "path": "", "value": current}]
        elif current is None:
            patch = [{"op": "replace", "path": "", "value": None}]
        else:
            patch = cast(
                list[dict[str, Any]],
                jsonpatch.make_patch(previous, current).patch,  # pyright: ignore[reportUnknownMemberType]
            )
        # Imported adoption-time data must have an explicit baseline before edits.
        exists = await session.scalar(
            select(ContentRevision.id)
            .where(ContentRevision.entity_type == kind, ContentRevision.entity_id == identifier)
            .limit(1)
        )
        if previous is not None and exists is None:
            raise RuntimeError(
                "Content history baseline missing; pause writes and run --baseline-content"
            )
        pending.append(ContentRevision(entity_type=kind, entity_id=identifier, op=patch))
    if not pending:
        return None
    started = perf_counter()
    await transaction_lock(session, PUBLICATION_KEY)
    logger.info(
        "content_publication_lock",
        wait_ms=round((perf_counter() - started) * 1000, 2),
        revisions=len(pending),
    )
    session.add_all(pending)
    await session.flush()
    return pending[-1].id


async def replay_many(
    session: AsyncSession, kind: EntityType, identifiers: Iterable[int], through: int | None = None
) -> dict[int, Snapshot]:
    values: dict[int, Snapshot] = dict.fromkeys(identifiers)
    if not values:
        return values
    statement = (
        select(ContentRevision.entity_id, ContentRevision.op)
        .where(ContentRevision.entity_type == kind, ContentRevision.entity_id.in_(values))
        .order_by(ContentRevision.id)
    )
    if through is not None:
        statement = statement.where(ContentRevision.id <= through)
    # History grows indefinitely; stream patches instead of loading the full chains.
    async for identifier, patch in await session.stream(statement):
        value = values[identifier]
        source = (
            {}
            if value is None and patch[0].get("op") == "add" and patch[0].get("path") == ""
            else value
        )
        values[identifier] = cast(
            Snapshot,
            jsonpatch.apply_patch(source, patch, in_place=False),  # pyright: ignore[reportUnknownMemberType]
        )
    return values


async def replay(
    session: AsyncSession, kind: EntityType, identifier: int, through: int | None = None
) -> Snapshot:
    return (await replay_many(session, kind, [identifier], through))[identifier]


async def head(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.coalesce(func.max(ContentRevision.id), 0))) or 0)


async def baseline(sessions: async_sessionmaker[AsyncSession], batch_size: int = 100) -> int:
    """Explicit bounded adoption backfill; the operator must pause content writes."""
    from pycil.study.models import QuestionArtifact
    from pycil.themes.models import Theme
    from pycil.vocabulary.models import Word

    if type(batch_size) is not int or batch_size <= 0:
        raise ValueError("Baseline batch size must be positive")
    count = 0
    entities: tuple[tuple[EntityType, type[Theme | Word | QuestionArtifact]], ...] = (
        ("theme", Theme),
        ("word", Word),
        ("question_artifact", QuestionArtifact),
    )
    for kind, model in entities:
        after = 0
        while True:
            async with sessions() as session, session.begin():
                identifiers = list(
                    await session.scalars(
                        select(model.id)
                        .where(model.id > after)
                        .order_by(model.id)
                        .limit(batch_size)
                    )
                )
                if not identifiers:
                    break
                before = await capture(session, [(kind, identifier) for identifier in identifiers])
                rows: list[ContentRevision] = []
                for (entity_type, identifier), value in before.items():
                    exists = await session.scalar(
                        select(ContentRevision.id)
                        .where(
                            ContentRevision.entity_type == entity_type,
                            ContentRevision.entity_id == identifier,
                        )
                        .limit(1)
                    )
                    if exists is None:
                        rows.append(
                            ContentRevision(
                                entity_type=entity_type,
                                entity_id=identifier,
                                op=[{"op": "add", "path": "", "value": value}],
                            )
                        )
                if rows:
                    await transaction_lock(session, PUBLICATION_KEY)
                    session.add_all(rows)
                    await session.flush()
                    count += len(rows)
                after = identifiers[-1]
    return count
