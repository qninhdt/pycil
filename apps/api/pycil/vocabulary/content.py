"""Transactional content edits/deletions; callers invalidate caches after commit."""

from collections.abc import Sequence

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.infrastructure.database import transaction_lock
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.vocabulary import models as v
from pycil.vocabulary.revisions import GRAPH_KEY, capture, publish
from pycil.vocabulary.schemas import CachedWord, Sense
from pycil.vocabulary.text import match_key, validate_lemma


async def edit_word(
    sessions: async_sessionmaker[AsyncSession],
    identifier: int,
    *,
    lemma: str | None = None,
    aliases: Sequence[str] | None = None,
    word_store: InMemoryStore[int, CachedWord] | None = None,
    sense_store: InMemoryStore[int, Sense] | None = None,
) -> int | None:
    normalized = validate_lemma(lemma) if lemma is not None else None
    names = [validate_lemma(alias) for alias in aliases] if aliases is not None else None
    async with sessions() as session, session.begin():
        before = await capture(session, [identifier])
        word = await session.get(v.Word, identifier)
        if word is None:
            raise ValueError("unknown word")
        if normalized is not None:
            word.lemma, word.match_key = normalized, match_key(normalized)
        if names is not None:
            # Preserve stable child IDs when unchanged; the snapshot keeps their identity.
            existing = {
                row.match_key: row
                for row in await session.scalars(
                    select(v.WordAlias).where(v.WordAlias.word_id == identifier)
                )
            }
            wanted = {match_key(name): name for name in names if match_key(name) != word.match_key}
            for key, row in existing.items():
                if key not in wanted:
                    await session.delete(row)
                else:
                    row.content = wanted[key]
            for key, name in wanted.items():
                if key not in existing:
                    session.add(v.WordAlias(word_id=identifier, content=name, match_key=key))
        revision = await publish(session, before)
    if revision is not None:
        for store in (word_store, sense_store):
            if store is not None:
                store.clear()
    return revision


async def delete_word(
    sessions: async_sessionmaker[AsyncSession],
    identifier: int,
    *,
    word_store: InMemoryStore[int, CachedWord] | None = None,
    sense_store: InMemoryStore[int, Sense] | None = None,
) -> int | None:
    async with sessions() as session, session.begin():
        # Stabilize inbound edges before choosing owners; publishers take this lock first too.
        await transaction_lock(session, GRAPH_KEY)
        # Inbound edges are semantic content of their source words too.
        sense_ids = select(v.Sense.id).where(v.Sense.word_id == identifier)
        affected = set(
            await session.scalars(
                select(v.WordRelation.from_word_id).where(v.WordRelation.to_word_id == identifier)
            )
        )
        affected.update(
            await session.scalars(
                select(v.Sense.word_id)
                .join(v.SenseRelation, v.SenseRelation.from_sense_id == v.Sense.id)
                .where(
                    or_(
                        v.SenseRelation.to_word_id == identifier,
                        v.SenseRelation.to_sense_id.in_(sense_ids),
                    )
                )
            )
        )
        before = await capture(session, affected | {identifier})
        if before.get(identifier) is None:
            return None
        await session.execute(delete(v.Word).where(v.Word.id == identifier))
        revision = await publish(session, before)
    if revision is not None:
        for store in (word_store, sense_store):
            if store is not None:
                store.clear()
    return revision
