"""Budgeted request-local graph expansion; sense sets remain in PostgreSQL."""

import asyncio
from dataclasses import dataclass, field
from time import monotonic
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from pycil.http import Problem
from pycil.library.access import readable, reference_visible
from pycil.library.models import DeckSense, Node, NodePath, NodeRole, NodeType


@dataclass
class ScopeBudget:
    """Pass the same budget to every scope in a batched request."""

    viewer_id: UUID | None
    nodes: set[UUID] = field(default_factory=set)
    decks: set[UUID] = field(default_factory=set)
    memberships: int = 0
    types: dict[UUID, NodeType] = field(default_factory=dict)
    edges: dict[UUID, set[UUID]] = field(default_factory=dict)
    started_at: float = field(default_factory=monotonic)


async def scope_ids(session, node_id, viewer_id, config, *, budget=None):
    budget = budget or ScopeBudget(viewer_id)
    if budget.viewer_id != viewer_id:
        raise ValueError("scope_budget_viewer_mismatch")
    remaining_time = config.library.scope_timeout_seconds - (monotonic() - budget.started_at)
    if remaining_time <= 0:
        raise Problem(503, "scope_timeout")
    try:
        async with asyncio.timeout(remaining_time):
            await session.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {"timeout": f"{config.library.statement_timeout_ms}ms"},
            )
            return await _expand(session, node_id, viewer_id, config, budget)
    except TimeoutError:
        raise Problem(503, "scope_timeout") from None
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) == "57014":
            raise Problem(503, "scope_timeout") from None
        raise


async def _expand(session, node_id, viewer_id, config, budget):
    if node_id is None:
        node_id = await session.scalar(
            select(Node.id).where(
                Node.owner_id == viewer_id,
                Node.role == NodeRole.LIBRARY_ROOT,
            )
        )
    root = await readable(session, node_id, viewer_id, config)
    frontier, visited, decks = {root.id}, set(), set()
    while frontier:
        unknown = frontier - budget.nodes
        if unknown:
            paths = select(NodePath.descendant_id).where(NodePath.ancestor_id.in_(unknown))
            query = select(Node).where(
                Node.id.in_(paths),
                Node.deleted_at.is_(None),
                ~Node.id.in_(budget.nodes),
            )
            available = config.library.max_scope_nodes - len(budget.nodes)
            rows = list((await session.scalars(query.limit(available + 1))).all())
            if len(rows) > available:
                raise Problem(422, "scope_too_large")
            references, unchecked = [], set()
            for node in rows:
                budget.nodes.add(node.id)
                budget.types[node.id] = node.type
                if node.parent_id is not None:
                    budget.edges.setdefault(node.parent_id, set()).add(node.id)
                if node.type is NodeType.REFERENCE:
                    references.append(node.id)
                if node.type is NodeType.DECK:
                    unchecked.add(node.id)
            if references:
                for source, target in (
                    await session.execute(
                        select(Node.id, Node.reference_id).where(
                            Node.id.in_(references),
                            reference_visible(Node.__table__, viewer_id),
                        )
                    )
                ).all():
                    budget.edges.setdefault(source, set()).add(target)
            if unchecked:
                guard = (
                    select(DeckSense.sense_id)
                    .where(DeckSense.deck_id.in_(unchecked))
                    .limit(config.library.max_scope_memberships - budget.memberships + 1)
                    .subquery()
                )
                budget.memberships += await session.scalar(select(func.count()).select_from(guard))
                if budget.memberships > config.library.max_scope_memberships:
                    raise Problem(422, "scope_too_large")
                budget.decks.update(unchecked)
        next_frontier = set()
        for identifier in frontier:
            if identifier not in budget.nodes:
                continue
            visited.add(identifier)
            if budget.types[identifier] is NodeType.DECK:
                decks.add(identifier)
            next_frontier.update(budget.edges.get(identifier, ()))
        frontier = next_frontier - visited
    return select(DeckSense.sense_id).where(DeckSense.deck_id.in_(decks)).distinct()
