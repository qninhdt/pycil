"""Paginated live learning views enriched through one native dictionary batch."""

from datetime import UTC, datetime

from sqlalchemy import and_, select

from pycil.http import Problem
from pycil.library.scope import scope_ids
from pycil.study.models import SenseMemory


async def member_ids(session, node, viewer_id, config):
    return await scope_ids(session, node.id, viewer_id, config)


async def sense_page(session, node, viewer_id, config, lexicon, after_id=0, *, state="ALL"):
    if state != "ALL" and viewer_id is None:
        raise Problem(401, "authentication_required")
    now = datetime.now(UTC)
    scope = (await member_ids(session, node, viewer_id, config)).subquery()
    query = select(scope.c.sense_id)
    if state != "ALL":
        query = query.outerjoin(
            SenseMemory,
            and_(
                SenseMemory.user_id == viewer_id,
                SenseMemory.sense_id == scope.c.sense_id,
            ),
        )
        query = query.where(
            {
                "NEW": SenseMemory.sense_id.is_(None),
                "DUE": SenseMemory.due_at <= now,
                "NOT_YET_DUE": SenseMemory.due_at > now,
            }[state]
        )
    rows = list(
        (
            await session.scalars(
                query.where(scope.c.sense_id > after_id)
                .order_by(scope.c.sense_id)
                .limit(config.library.page_size + 1)
            )
        ).all()
    )
    identifiers = rows[: config.library.page_size]
    facts = {fact["sense_id"]: dict(fact) for fact in await lexicon.get_sense_previews(identifiers)}
    memory = {}
    if viewer_id is not None and identifiers:
        memory = {
            m.sense_id: m
            for m in (
                await session.scalars(
                    select(SenseMemory).where(
                        SenseMemory.user_id == viewer_id,
                        SenseMemory.sense_id.in_(identifiers),
                    )
                )
            ).all()
        }
    items = []
    for identifier in identifiers:
        if identifier not in facts:
            raise Problem(409, "learning_content_changed")
        item = facts[identifier]
        learning = memory.get(identifier)
        item["learning"] = (
            None
            if viewer_id is None
            else {
                "state": "NEW"
                if learning is None
                else "DUE"
                if learning.due_at <= now
                else "NOT_YET_DUE",
                "due_at": learning.due_at if learning else None,
                "last_rating": learning.last_rating if learning else None,
            }
        )
        items.append(item)
    return {
        "senses": items,
        "as_of": now,
        "next_after_id": identifiers[-1] if len(rows) > len(identifiers) else None,
    }
