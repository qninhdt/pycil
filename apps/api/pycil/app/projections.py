from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.app.config import AppConfig
from pycil.app.http import Problem
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.library.schemas import LearningPreview, SourceDeck
from pycil.library.scope import ScopeBudget, bounded, resolve_scopes
from pycil.library.senses import learning_preview, source_batch
from pycil.library.types import SenseSourcesSummary
from pycil.study.models import UserSense
from pycil.utils.schemas import PositiveID, Strict
from pycil.vocabulary.enums import EntryType
from pycil.vocabulary.models import Sense, Word
from pycil.vocabulary.schemas import Sense as NativeSense
from pycil.vocabulary.words import get_senses


class WordIDs(Strict):
    word_ids: list[PositiveID] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.word_ids)) != len(self.word_ids):
            raise ValueError("duplicate word IDs")
        return self


class SenseIDs(Strict):
    sense_ids: list[PositiveID] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.sense_ids)) != len(self.sense_ids):
            raise ValueError("duplicate sense IDs")
        return self


class WordPreview(Strict):
    word_id: int
    lemma: str
    entry_type: EntryType
    senses: list[NativeSense]


class SenseContext(Strict):
    sense_id: int
    learning: LearningPreview
    decks: list[SourceDeck]
    deck_count: int
    decks_has_more: bool


class Context(Strict):
    as_of: datetime
    senses: list[SenseContext]
    total: int
    studied: int
    new: int
    due: int
    not_due: int


async def word_previews(
    session: AsyncSession,
    sessions: async_sessionmaker[AsyncSession],
    identifiers: Sequence[int],
    config: AppConfig,
    *,
    sense_store: InMemoryStore[int, NativeSense] | None = None,
) -> list[dict[str, object]]:
    if len(identifiers) > config.product.projections.max_word_ids:
        raise Problem(422, "lexical_batch_too_large")
    words = {
        w.id: w for w in (await session.scalars(select(Word).where(Word.id.in_(identifiers)))).all()
    }
    if set(words) != set(identifiers):
        raise Problem(404, "word_not_found")
    rows = list(
        (
            await session.execute(
                select(Sense.id, Sense.word_id)
                .where(Sense.word_id.in_(identifiers))
                .order_by(Sense.id)
                .limit(config.product.projections.max_word_senses + 1)
            )
        ).all()
    )
    if len(rows) > config.product.projections.max_word_senses:
        raise Problem(422, "lexical_batch_too_large")
    native = {s.id: s for s in await get_senses(sessions, [r.id for r in rows], store=sense_store)}
    if set(native) != {r.id for r in rows}:
        raise Problem(409, "learning_content_changed")
    groups: dict[int, list[NativeSense]] = {i: [] for i in identifiers}
    for row in rows:
        groups[row.word_id].append(
            replace(
                native[row.id],
                examples=native[row.id].examples[: config.product.projections.inline_examples],
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
    config: AppConfig,
    identifiers: Sequence[int],
    *,
    include_sources: bool = True,
    max_senses: int | None = None,
) -> dict[str, object]:
    if len(identifiers) > (max_senses or config.product.projections.max_context_senses) or len(
        set(identifiers)
    ) != len(identifiers):
        raise Problem(422, "context_too_large")
    found = set((await session.scalars(select(Sense.id).where(Sense.id.in_(identifiers)))).all())
    if found != set(identifiers):
        raise Problem(404, "sense_not_found")
    budget = ScopeBudget(user_id)
    async with bounded(session, config, budget):
        scope = (
            next(
                iter(
                    (await resolve_scopes(session, [None], user_id, config, budget=budget)).values()
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
        membership: dict[int, SenseSourcesSummary] = (
            await source_batch(session, scope.decks, identifiers, user_id, config)
            if scope
            else {i: {"decks": [], "count": 0} for i in identifiers}
        )
        now = datetime.now(UTC)
        senses = [
            {
                "sense_id": identifier,
                "learning": learning_preview(memories.get(identifier), now, user_id, config),
                "decks": membership[identifier]["decks"],
                "deck_count": membership[identifier]["count"],
                "decks_has_more": int(membership[identifier]["count"])
                > config.product.projections.inline_sources,
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
    session: AsyncSession, user_id: UUID, config: AppConfig, word_id: int
) -> dict[str, object]:
    if await session.get(Word, word_id) is None:
        raise Problem(404, "word_not_found")
    identifiers = list(
        (
            await session.scalars(
                select(Sense.id)
                .where(Sense.word_id == word_id)
                .order_by(Sense.id)
                .limit(config.product.projections.max_context_senses + 1)
            )
        ).all()
    )
    return await viewer_context(session, user_id, config, identifiers)
