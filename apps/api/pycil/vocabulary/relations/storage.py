"""Bounded pending-edge selection and snapshot-checked neutral evidence publication."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import and_, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from pycil.infrastructure.content_revisions import GRAPH_KEY, capture, publish
from pycil.infrastructure.database import transaction_lock
from pycil.utils.hashing import sha256_hex
from pycil.vocabulary.enums import GenerationState, PartOfSpeech, SenseRelationType
from pycil.vocabulary.models import Definition, Sense, SenseRelation, Word


class ClearableStore(Protocol):
    def clear(self) -> None: ...


@dataclass(frozen=True)
class Candidate:
    id: int
    pos: PartOfSpeech
    definition: str | None

    @property
    def fingerprint(self) -> str | None:
        return sha256_hex(self.definition) if self.definition is not None else None


@dataclass(frozen=True)
class PendingLink:
    edge_id: int
    source_word: str
    source_definition: str | None
    source_pos: PartOfSpeech
    relation_type: SenseRelationType
    target_word: str
    candidates: tuple[Candidate, ...]


async def evidence(session: AsyncSession, identifiers: Sequence[int]) -> list[PendingLink]:
    source_word, target_word = aliased(Word), aliased(Word)
    rows = (
        await session.execute(
            select(
                SenseRelation.id,
                source_word.lemma,
                Definition.content,
                Sense.pos,
                SenseRelation.rel_type,
                target_word.lemma,
                target_word.id,
            )
            .join(Sense, Sense.id == SenseRelation.from_sense_id)
            .join(source_word, source_word.id == Sense.word_id)
            .join(target_word, target_word.id == SenseRelation.to_word_id)
            .outerjoin(
                Definition, and_(Definition.sense_id == Sense.id, Definition.theme_id.is_(None))
            )
            .where(
                SenseRelation.id.in_(identifiers),
                target_word.generation_state == GenerationState.DONE,
            )
            .order_by(SenseRelation.id)
        )
    ).all()
    scopes: set[tuple[int, PartOfSpeech]] = {(row[6], row[3]) for row in rows}
    candidates: dict[tuple[int, PartOfSpeech], list[Candidate]] = {scope: [] for scope in scopes}
    if scopes:
        for word_id, pos, identifier, definition in await session.execute(
            select(Sense.word_id, Sense.pos, Sense.id, Definition.content)
            .outerjoin(
                Definition, and_(Definition.sense_id == Sense.id, Definition.theme_id.is_(None))
            )
            .where(tuple_(Sense.word_id, Sense.pos).in_(scopes))
            .order_by(Sense.id)
        ):
            candidates[word_id, pos].append(Candidate(identifier, pos, definition))
    return [
        PendingLink(
            edge_id=row[0],
            source_word=row[1],
            source_definition=row[2],
            source_pos=row[3],
            relation_type=row[4],
            target_word=row[5],
            candidates=tuple(candidates[row[6], row[3]]),
        )
        for row in rows
    ]


async def pending_relations(
    sessions: async_sessionmaker[AsyncSession], batch_size: int
) -> list[PendingLink]:
    if type(batch_size) is not int or not 1 <= batch_size <= 50:
        raise ValueError("relation batch size must be between 1 and 50")
    # Seek distinct pending targets so ungenerated targets cannot starve ready edges.
    statement = text("""
        WITH RECURSIVE targets(word_id) AS (
            SELECT (SELECT to_word_id FROM sense_relations
                    WHERE resolve_attempted_at IS NULL ORDER BY to_word_id LIMIT 1)
            UNION ALL
            SELECT (SELECT to_word_id FROM sense_relations
                    WHERE resolve_attempted_at IS NULL AND to_word_id > targets.word_id
                    ORDER BY to_word_id LIMIT 1)
            FROM targets WHERE word_id IS NOT NULL
        ), ready AS MATERIALIZED (
            SELECT words.id FROM targets JOIN words ON words.id = targets.word_id
            WHERE words.generation_state = :done
              AND EXISTS (SELECT 1 FROM senses WHERE word_id = words.id)
        )
        SELECT edges.id FROM ready CROSS JOIN LATERAL (
            SELECT id FROM sense_relations WHERE to_word_id = ready.id
                AND resolve_attempted_at IS NULL ORDER BY id LIMIT :batch
        ) edges ORDER BY edges.id LIMIT :batch
    """)
    async with sessions() as session:
        identifiers = list(
            (
                await session.scalars(
                    statement, {"batch": batch_size, "done": GenerationState.DONE.value}
                )
            ).all()
        )
        return await evidence(session, identifiers) if identifiers else []


async def apply_resolution(
    sessions: async_sessionmaker[AsyncSession],
    expected: PendingLink,
    selected: Candidate | None,
    *,
    store: ClearableStore | None = None,
) -> bool:
    async with sessions() as session, session.begin():
        await transaction_lock(session, GRAPH_KEY)
        owner_id = await session.scalar(
            select(Sense.word_id)
            .join(SenseRelation, SenseRelation.from_sense_id == Sense.id)
            .where(SenseRelation.id == expected.edge_id)
        )
        if owner_id is None:
            return False
        before = await capture(session, [("word", owner_id)])
        edge = await session.scalar(
            select(SenseRelation).where(SenseRelation.id == expected.edge_id).with_for_update()
        )
        if edge is None:
            return False
        current = await evidence(session, [expected.edge_id])
        if not current or current[0] != expected or expected.source_definition is None:
            return False
        if any(candidate.definition is None for candidate in current[0].candidates):
            return False
        if selected is not None and selected not in current[0].candidates:
            return False
        edge.to_sense_id = selected.id if selected is not None else None
        edge.target_hash = selected.fingerprint if selected is not None else None
        edge.resolve_attempted_at = datetime.now(UTC).isoformat()
        await publish(session, before)
    if store is not None:
        store.clear()
    return True
