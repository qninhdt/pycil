"""Scoped searchable pages with batched native content and authorized provenance."""

from datetime import UTC, datetime

from lexi_ai.contract import Sense, Word
from sqlalchemy import and_, func, or_, select, tuple_

from pycil.http import Problem
from pycil.library.models import DeckSense, Node
from pycil.library.scope import ScopeBudget, bounded, resolve_scopes, scope_ids
from pycil.pagination import decode, encode, includes, page_limit
from pycil.study.models import UserSense


async def member_ids(session, node, viewer_id, config):
    return await scope_ids(session, node.id, viewer_id, config)


def learning_preview(memory, now, viewer_id):
    if viewer_id is None:
        return None
    return {
        "state": "NEW" if memory is None else "DUE" if memory.due_at <= now else "NOT_YET_DUE",
        "due_at": memory.due_at if memory else None,
        "last_rating": memory.last_rating if memory else None,
        "last_reviewed_at": memory.last_review_at if memory else None,
    }


def source(row, viewer_id):
    return {
        "id": row.id,
        "name": row.name,
        "owner_id": row.owner_id,
        "space": row.space,
        "editable": row.owner_id == viewer_id,
    }


async def source_batch(session, decks, identifiers, viewer_id, config):
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
    result = {i: {"decks": [], "count": 0} for i in identifiers}
    for row in (
        await session.execute(
            select(ranked).where(ranked.c.position <= config.projections.inline_sources)
        )
    ).all():
        result[row.sense_id]["decks"].append(source(row, viewer_id))
        result[row.sense_id]["count"] = row.total
    return result


async def sources_page(session, node_id, sense_id, viewer_id, config, cursor=None, limit=None):
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
    session,
    node,
    viewer_id,
    config,
    lexicon,
    cursor=None,
    *,
    state="ALL",
    q=None,
    sort="SENSE_ID_ASC",
    limit=None,
    include=None,
):
    if (state != "ALL" or sort == "LAST_REVIEWED_DESC") and viewer_id is None:
        raise Problem(401, "authentication_required")
    if state not in {"ALL", "NEW", "DUE", "NOT_YET_DUE"} or sort not in {
        "SENSE_ID_ASC",
        "LEMMA_ASC",
        "LAST_REVIEWED_DESC",
    }:
        raise Problem(422, "invalid_sense_filter")
    if q is not None and len(q) > config.projections.max_query_chars:
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
        "SENSE_ID_ASC": ["id"],
        "LEMMA_ASC": ["text", "id"],
        "LAST_REVIEWED_DESC": ["nullable_time", "id"],
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
        query = (
            select(Sense.id, lemma.label("lemma_key"), UserSense.last_review_at)
            .join(membership, membership.c.sense_id == Sense.id)
            .join(Word, Word.id == Sense.word_id)
            .outerjoin(
                UserSense, and_(UserSense.user_id == viewer_id, UserSense.sense_id == Sense.id)
            )
        )
        if state != "ALL":
            query = query.where(
                {
                    "NEW": UserSense.sense_id.is_(None),
                    "DUE": UserSense.due_at <= now,
                    "NOT_YET_DUE": UserSense.due_at > now,
                }[state]
            )
        if q:
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.where(Word.lemma.ilike(f"%{escaped}%", escape="\\"))
        if sort == "SENSE_ID_ASC":
            ordering = [Sense.id]
            if seek:
                query = query.where(Sense.id > seek[0])
        elif sort == "LEMMA_ASC":
            ordering = [lemma, Sense.id]
            if seek:
                query = query.where(tuple_(lemma, Sense.id) > tuple_(*seek))
        else:
            ordering = [UserSense.last_review_at.desc().nulls_last(), Sense.id]
            if seek:
                at, identifier = seek
                condition = (
                    and_(UserSense.last_review_at.is_(None), Sense.id > identifier)
                    if at is None
                    else or_(
                        UserSense.last_review_at < at,
                        UserSense.last_review_at.is_(None),
                        and_(UserSense.last_review_at == at, Sense.id > identifier),
                    )
                )
                query = query.where(condition)
        rows = list((await session.execute(query.order_by(*ordering).limit(limit + 1))).all())
        page = rows[:limit]
        identifiers = [r.id for r in page]
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
    facts = {fact["sense_id"]: dict(fact) for fact in await lexicon.get_sense_previews(identifiers)}
    native = (
        {s.id: s for s in await lexicon.get_senses(identifiers)} if "examples" in enrichment else {}
    )
    items = []
    for identifier in identifiers:
        if identifier not in facts or "examples" in enrichment and identifier not in native:
            raise Problem(409, "learning_content_changed")
        item = facts[identifier] | {
            "learning": learning_preview(memories.get(identifier), now, viewer_id)
        }
        if "examples" in enrichment:
            item["examples"] = native[identifier].examples[: config.projections.inline_examples]
        if "sources" in enrichment:
            item |= {
                "sources": sources[identifier]["decks"],
                "source_count": sources[identifier]["count"],
                "sources_has_more": sources[identifier]["count"]
                > config.projections.inline_sources,
            }
        items.append(item)
    last = page[-1] if page else None
    anchor = (
        [last.id]
        if sort == "SENSE_ID_ASC" and last
        else [last.lemma_key, last.id]
        if sort == "LEMMA_ASC" and last
        else [last.last_review_at, last.id]
        if last
        else []
    )
    return {
        "senses": items,
        "as_of": now,
        "next_cursor": encode(binding, anchor, as_of=now) if len(rows) > limit else None,
    }
