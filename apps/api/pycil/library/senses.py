"""Live scope/memory reads assembled with Lexi's cached, bulk UI facts."""

from datetime import UTC, datetime

from sqlalchemy import select

from pycil.http import Problem
from pycil.library.access import scope_ids
from pycil.library.models import DeckSense, NodeType
from pycil.study.fsrs import mastery
from pycil.study.models import SenseMemory


def member_ids(node, viewer_id, config):
    """The caller has authorized this node through the shared live access path."""
    if node.type is NodeType.DECK:
        return select(DeckSense.sense_id).where(DeckSense.deck_id == node.id)
    return scope_ids(node.id, viewer_id, config)


async def sense_page(session, node, viewer_id, config, lexicon, after_id=0, *, snapshot=None):
    from pycil.library.nodes import deck_snapshot

    is_deck = node.type is NodeType.DECK
    if is_deck:
        if after_id:
            raise Problem(422, "deck_cursor_not_supported")
        snapshot = snapshot or await deck_snapshot(session, node)
        identifiers = snapshot.sense_ids
        more = False
    else:
        scope = member_ids(node, viewer_id, config).subquery()
        rows = list(
            (
                await session.scalars(
                    select(scope.c.sense_id)
                    .where(scope.c.sense_id > after_id)
                    .order_by(scope.c.sense_id)
                    .limit(config.library.page_size + 1)
                )
            ).all()
        )
        more = len(rows) > config.library.page_size
        identifiers = rows[: config.library.page_size]
    facts = await lexicon.get_sense_previews(identifiers)
    memory = {}
    if viewer_id is not None and identifiers:
        # Chunk large, pre-existing oversized decks without per-Sense queries.
        for start in range(0, len(identifiers), 500):
            memory.update(
                {
                    m.sense_id: m
                    for m in (
                        await session.scalars(
                            select(SenseMemory).where(
                                SenseMemory.user_id == viewer_id,
                                SenseMemory.sense_id.in_(identifiers[start : start + 500]),
                            )
                        )
                    ).all()
                }
            )
    now = datetime.now(UTC)
    items = []
    for fact in facts:
        item = dict(fact)
        state = memory.get(item["sense_id"])
        item["learning"] = (
            None
            if viewer_id is None
            else {
                "state": "NEW"
                if state is None
                else "DUE"
                if state.due_at <= now
                else "NOT_YET_DUE",
                "mastery": mastery(state.stability, config) if state is not None else 0,
                "due_at": state.due_at if state is not None else None,
                "last_rating": state.last_rating if state is not None else None,
            }
        )
        items.append(item)
    result = {"senses": items}
    if not is_deck:
        result["next_after_id"] = identifiers[-1] if more else None
    return result
