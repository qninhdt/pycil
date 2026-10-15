from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import Select

from pycil.app.config import AppConfig
from pycil.app.http import Problem
from pycil.app.pagination import decode, encode, includes, page_limit
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.library.models import DeckSense, Node, NodeSpace
from pycil.library.schemas import SenseSort
from pycil.library.scope import ScopeBudget, bounded, resolve_scopes, scope_ids
from pycil.library.types import (
    LearningPreviewDict,
    SenseSourcesSummary,
    SourceDeckDict,
    SourcesPageDict,
)
from pycil.study.enums import LearningState
from pycil.study.models import UserSense
from pycil.vocabulary.models import Sense, Word
from pycil.vocabulary.schemas import Sense as NativeSense
from pycil.vocabulary.words import get_sense_previews, get_senses


async def member_ids(
    session: AsyncSession, node: Node, viewer_id: UUID | None, config: AppConfig
) -> Select[int]:
    return await scope_ids(session, node.id, viewer_id, config)


def learning_preview(
    memory: UserSense | None,
    now: datetime,
    viewer_id: UUID | None,
    config: AppConfig,
) -> LearningPreviewDict | None:
    if viewer_id is None:
        return None
    return {
        "state": LearningState.NEW
        if memory is None
        else LearningState.DUE
        if memory.due_at <= now
        else LearningState.NOT_YET_DUE,
        "due_at": memory.due_at if memory else None,
        "elo": memory.elo if memory else None,
        "level": config.product.study.mastery.level(memory.elo) if memory else None,
        "last_reviewed_at": memory.last_exposure_at if memory else None,
    }


def source_dict(
    node_id: UUID, name: str, owner_id: UUID | None, space: NodeSpace, viewer_id: UUID | None
) -> SourceDeckDict:
    return {
        "id": node_id,
        "name": name,
        "owner_id": owner_id,
        "space": space,
        "editable": owner_id == viewer_id,
    }


def source(row: Node, viewer_id: UUID | None) -> SourceDeckDict:
    return source_dict(row.id, row.name, row.owner_id, row.space, viewer_id)


async def source_batch(
    session: AsyncSession,
    decks: Sequence[UUID] | set[UUID],
    identifiers: Sequence[int],
    viewer_id: UUID | None,
    config: AppConfig,
) -> dict[int, SenseSourcesSummary]:
    ranked = (
        select(
            DeckSense.sense_id,
            Node.id,
            Node.name,
            Node.owner_id,
            Node.space,
            func.row_number()
            .over(partition_by=DeckSense.sense_id, order_by=Node.id)
            .label("position"),
            func.count().over(partition_by=DeckSense.sense_id).label("total"),
        )
        .join(Node, Node.id == DeckSense.deck_id)
        .where(DeckSense.deck_id.in_(decks), DeckSense.sense_id.in_(identifiers))
        .subquery()
    )
    result: dict[int, SenseSourcesSummary] = {i: {"decks": [], "count": 0} for i in identifiers}
    for row in (
        await session.execute(
            select(ranked).where(ranked.c.position <= config.product.projections.inline_sources)
        )
    ).all():
        sense_id: int = int(row[0])
        node_id: UUID = cast(UUID, row[1])
        name: str = str(row[2])
        owner_id: UUID | None = cast(UUID | None, row[3])
        space: NodeSpace = cast(NodeSpace, row[4])
        total: int = int(row[6])
        result[sense_id]["decks"].append(source_dict(node_id, name, owner_id, space, viewer_id))
        result[sense_id]["count"] = total
    return result


async def sources_page(
    session: AsyncSession,
    node_id: UUID | None,
    sense_id: int,
    viewer_id: UUID | None,
    config: AppConfig,
    cursor: str | None = None,
    limit: int | None = None,
) -> SourcesPageDict:
    limit = page_limit(limit, config)
    binding = {
        "kind": "sources",
        "viewer": str(viewer_id),
        "scope": str(node_id),
        "sense": sense_id,
    }
    seek, _ = decode(cursor, binding, ["uuid"])
    budget = ScopeBudget(viewer_id)
    async with bounded(session, config, budget):
        scope = next(
            iter(
                (
                    await resolve_scopes(session, [node_id], viewer_id, config, budget=budget)
                ).values()
            )
        )
        query = (
            select(Node)
            .join(DeckSense, DeckSense.deck_id == Node.id)
            .where(Node.id.in_(scope.decks), DeckSense.sense_id == sense_id)
        )
        if seek:
            query = query.where(Node.id > seek[0])
        rows = list((await session.scalars(query.order_by(Node.id).limit(limit + 1))).all())
        page = rows[:limit]
        return {
            "decks": [source(row, viewer_id) for row in page],
            "next_cursor": encode(binding, [page[-1].id]) if len(rows) > limit else None,
        }


async def sense_page(
    session: AsyncSession,
    node: Node,
    viewer_id: UUID | None,
    config: AppConfig,
    sessions: async_sessionmaker[AsyncSession],
    cursor: str | None = None,
    *,
    state: LearningState = LearningState.ALL,
    q: str | None = None,
    sort: SenseSort = SenseSort.SENSE_ID_ASC,
    limit: int | None = None,
    include: str | None = None,
    sense_store: InMemoryStore[int, NativeSense] | None = None,
) -> dict[str, object]:
    if (
        state != LearningState.ALL or sort in {SenseSort.LAST_REVIEWED_DESC, SenseSort.MASTERY_ASC}
    ) and viewer_id is None:
        raise Problem(401, "authentication_required")
    if state not in {
        LearningState.ALL,
        LearningState.NEW,
        LearningState.DUE,
        LearningState.NOT_YET_DUE,
    } or sort not in {
        SenseSort.SENSE_ID_ASC,
        SenseSort.LEMMA_ASC,
        SenseSort.LAST_REVIEWED_DESC,
        SenseSort.MASTERY_ASC,
    }:
        raise Problem(422, "invalid_sense_filter")
    if q is not None and len(q) > config.product.projections.max_query_chars:
        raise Problem(422, "invalid_query")
    q = q.strip() if q else None
    limit = page_limit(limit, config)
    enrichment = includes(include, {"examples", "sources"})
    binding = {
        "kind": "senses",
        "viewer": str(viewer_id),
        "scope": str(node.id),
        "state": state,
        "q": q,
        "sort": sort,
    }
    kinds = {
        SenseSort.SENSE_ID_ASC: ["id"],
        SenseSort.LEMMA_ASC: ["text", "id"],
        SenseSort.LAST_REVIEWED_DESC: ["nullable_time", "id"],
        SenseSort.MASTERY_ASC: ["number", "id"],
    }[sort]
    seek, cutoff = decode(cursor, binding, kinds, timed=True)
    now = cutoff or datetime.now(UTC)
    budget = ScopeBudget(viewer_id)
    async with bounded(session, config, budget):
        scope = next(
            iter(
                (
                    await resolve_scopes(session, [node.id], viewer_id, config, budget=budget)
                ).values()
            )
        )
        membership = scope.senses().subquery()
        lemma = func.lower(Word.lemma)
        elo = func.coalesce(UserSense.elo, config.product.study.mastery.initial_elo)
        query = (
            select(Sense.id, lemma.label("lemma_key"), UserSense.last_exposure_at, elo.label("elo"))
            .join(membership, membership.c.sense_id == Sense.id)
            .join(Word, Word.id == Sense.word_id)
            .outerjoin(
                UserSense, and_(UserSense.user_id == viewer_id, UserSense.sense_id == Sense.id)
            )
        )
        if state != LearningState.ALL:
            query = query.where(
                {
                    LearningState.NEW: UserSense.sense_id.is_(None),
                    LearningState.DUE: UserSense.due_at <= now,
                    LearningState.NOT_YET_DUE: UserSense.due_at > now,
                }[state]
            )
        if q:
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.where(Word.lemma.ilike(f"%{escaped}%", escape="\\"))
        if sort == SenseSort.SENSE_ID_ASC:
            ordering = [Sense.id]
            if seek:
                query = query.where(Sense.id > seek[0])
        elif sort == SenseSort.LEMMA_ASC:
            ordering = [lemma, Sense.id]
            if seek:
                query = query.where(tuple_(lemma, Sense.id) > tuple_(*seek))
        elif sort == SenseSort.MASTERY_ASC:
            ordering = [elo, Sense.id]
            if seek:
                query = query.where(tuple_(elo, Sense.id) > tuple_(*seek))
        else:
            ordering = [UserSense.last_exposure_at.desc().nulls_last(), Sense.id]
            if seek:
                at, identifier = seek
                condition = (
                    and_(UserSense.last_exposure_at.is_(None), Sense.id > identifier)
                    if at is None
                    else or_(
                        UserSense.last_exposure_at < at,
                        UserSense.last_exposure_at.is_(None),
                        and_(UserSense.last_exposure_at == at, Sense.id > identifier),
                    )
                )
                query = query.where(condition)
        rows = list((await session.execute(query.order_by(*ordering).limit(limit + 1))).all())
        page = rows[:limit]
        identifiers: list[int] = [int(r[0]) for r in page]
        memories = (
            {
                m.sense_id: m
                for m in (
                    await session.scalars(
                        select(UserSense).where(
                            UserSense.user_id == viewer_id, UserSense.sense_id.in_(identifiers)
                        )
                    )
                ).all()
            }
            if viewer_id and identifiers
            else {}
        )
        sources = (
            await source_batch(session, scope.decks, identifiers, viewer_id, config)
            if "sources" in enrichment and identifiers
            else {}
        )
    facts = {
        fact["sense_id"]: dict(fact) for fact in await get_sense_previews(sessions, identifiers)
    }
    native = (
        {s.id: s for s in await get_senses(sessions, identifiers, store=sense_store)}
        if "examples" in enrichment
        else {}
    )
    items: list[dict[str, object]] = []
    for identifier in identifiers:
        if identifier not in facts or "examples" in enrichment and identifier not in native:
            raise Problem(409, "learning_content_changed")
        item: dict[str, object] = dict(facts[identifier]) | {
            "learning": learning_preview(memories.get(identifier), now, viewer_id, config)
        }
        if "examples" in enrichment:
            item["examples"] = native[identifier].examples[
                : config.product.projections.inline_examples
            ]
        if "sources" in enrichment:
            item |= {
                "sources": sources[identifier]["decks"],
                "source_count": sources[identifier]["count"],
                "sources_has_more": sources[identifier]["count"]
                > config.product.projections.inline_sources,
            }
        items.append(item)
    last = page[-1] if page else None
    anchor: list[object] = (
        [last[0]]
        if sort == SenseSort.SENSE_ID_ASC and last
        else [last[1], last[0]]
        if sort == SenseSort.LEMMA_ASC and last
        else [last[3], last[0]]
        if sort == SenseSort.MASTERY_ASC and last
        else [last[2], last[0]]
        if last
        else []
    )
    return {
        "senses": items,
        "as_of": now,
        "next_cursor": encode(binding, anchor, as_of=now) if len(rows) > limit else None,
    }
