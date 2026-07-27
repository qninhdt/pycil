"""A real query budget for the node listing: statements must not scale with rows.

This module is deliberately UNMARKED and lives outside ``tests/performance/``.
``tests/performance/test_hierarchy_query_budget.py`` is skipped unless
``RUN_HIERARCHY_PERFORMANCE=1``, which CI never sets, and it measures wall clock
rather than statements — so it is a benchmark that never runs, not a budget. A
statement counter is both deterministic and cheap, so it can run every time.

The failure this guards against is the one the whole rebuild exists to remove: a
listing that issues per-row queries. Comparing a page of 1 against a page of 50 is
what makes it visible; asserting an absolute number would just encode today's
implementation.
"""

import pytest
from sqlalchemy import event

from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.content import service as content_service
from pycil.hierarchy import service
from pycil.hierarchy.models import NodeType
from pycil.hierarchy.router import list_nodes

pytestmark = pytest.mark.asyncio

_PAGE = 50


class StatementCounter:
    """Counts statements actually sent to the driver for the duration of a block."""

    def __init__(self, engine):
        self._sync_engine = engine.sync_engine
        self.statements: list[str] = []

    def _on_execute(self, conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        self.statements.append(statement)

    def __enter__(self):
        event.listen(self._sync_engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *exc):
        event.remove(self._sync_engine, "before_cursor_execute", self._on_execute)
        return False

    def __len__(self) -> int:
        return len(self.statements)


async def _owner(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _folder_of_decks(session, owner_id, count: int, *, senses_each: int = 2):
    folder = await service.create_node(
        session, owner_id, node_type=NodeType.FOLDER, name=f"folder-{count}"
    )
    for index in range(count):
        deck = await service.create_node(
            session,
            owner_id,
            node_type=NodeType.DECK,
            name=f"deck-{index}",
            parent_node_id=folder.id,
        )
        for offset in range(senses_each):
            await content_service.add_sense(session, deck.id, index * 100 + offset)
    return folder


async def test_list_nodes_statement_count_is_independent_of_page_size(session, engine):
    owner = await _owner(session, "budget@example.com")
    one = await _folder_of_decks(session, owner.id, 1)
    many = await _folder_of_decks(session, owner.id, _PAGE)
    user = CurrentUser(id=owner.id, email=owner.email)

    with StatementCounter(engine) as counter_one:
        page_one = await list_nodes(
            user, session, parent_node_id=one.id, cursor=None, limit=_PAGE
        )
    with StatementCounter(engine) as counter_many:
        page_many = await list_nodes(
            user, session, parent_node_id=many.id, cursor=None, limit=_PAGE
        )

    assert len(page_one.items) == 1
    assert len(page_many.items) == _PAGE
    # Every deck row still reports a real count, so the constant statement count is
    # not achieved by simply not answering.
    assert all(item.item_count == 2 for item in page_many.items)

    assert len(counter_many) == len(counter_one), (
        f"{len(counter_many)} statements for {_PAGE} rows vs {len(counter_one)} for 1 — "
        "the listing is issuing per-row queries:\n"
        + "\n".join(counter_many.statements)
    )


async def test_deck_item_counts_are_one_statement_for_the_whole_page(session, engine):
    """Pins the mechanism, not just the symptom: one grouped aggregate."""
    from pycil.hierarchy.router import _deck_item_counts

    owner = await _owner(session, "budget-agg@example.com")
    folder = await _folder_of_decks(session, owner.id, _PAGE)
    deck_ids = [
        node.id
        for node in (
            await list_nodes(
                CurrentUser(id=owner.id, email=owner.email),
                session,
                parent_node_id=folder.id,
                cursor=None,
                limit=_PAGE,
            )
        ).items
    ]

    with StatementCounter(engine) as counter:
        counts = await _deck_item_counts(session, deck_ids)

    assert len(counts) == _PAGE
    assert len(counter) == 1, counter.statements


async def test_empty_page_costs_no_aggregate(session, engine):
    from pycil.hierarchy.router import _deck_item_counts

    with StatementCounter(engine) as counter:
        assert await _deck_item_counts(session, []) == {}
    assert len(counter) == 0
