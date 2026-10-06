"""Joint viewer-local graph expansion; no permission or scope cache survives a request."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from time import monotonic
from uuid import UUID

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.exc import DBAPIError

from pycil.http import Problem
from pycil.library.access import reference_visible, visible
from pycil.library.models import DeckSense, Node, NodePath, NodeRole, NodeType


@dataclass
class ScopeBudget:
    viewer_id: UUID | None
    nodes: set[UUID] = field(default_factory=set)
    decks: set[UUID] = field(default_factory=set)
    memberships: int = 0
    types: dict = field(default_factory=dict)
    edges: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    membership_counts: dict = field(default_factory=dict)
    started_at: float = field(default_factory=monotonic)


@dataclass
class Scope:
    root: Node
    nodes: set
    decks: set

    def senses(self):
        return select(DeckSense.sense_id).where(DeckSense.deck_id.in_(self.decks)).distinct()


@asynccontextmanager
async def bounded(session, config, budget):
    remaining = config.library.scope_timeout_seconds - (monotonic() - budget.started_at)
    if remaining <= 0:
        raise Problem(503, "scope_timeout")
    try:
        async with asyncio.timeout(remaining):
            await session.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {"timeout": f"{config.library.statement_timeout_ms}ms"},
            )
            yield
    except TimeoutError:
        raise Problem(503, "scope_timeout") from None
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) == "57014":
            raise Problem(503, "scope_timeout") from None
        raise


async def resolve_scopes(
    session,
    identifiers,
    viewer_id,
    config,
    *,
    budget=None,
    include_memberships=True,
    materialize_candidates=False,
):
    budget = budget or ScopeBudget(viewer_id)
    if viewer_id != budget.viewer_id:
        raise ValueError("scope_budget_viewer_mismatch")
    if None in identifiers:
        root = await session.scalar(
            select(Node.id).where(Node.owner_id == viewer_id, Node.role == NodeRole.LIBRARY_ROOT)
        )
        identifiers = [root if identifier is None else identifier for identifier in identifiers]
    roots = list(
        (
            await session.scalars(
                select(Node).where(
                    Node.id.in_(identifiers),
                    visible(Node.__table__, viewer_id),
                    or_(
                        Node.owner_id == viewer_id,
                        Node.type != NodeType.REFERENCE,
                        reference_visible(Node.__table__, viewer_id),
                    ),
                )
            )
        ).all()
    )
    if {r.id for r in roots} != set(identifiers):
        raise Problem(404, "node_not_found")
    frontier = set(identifiers) - budget.nodes
    while frontier:
        paths = select(NodePath.descendant_id).where(NodePath.ancestor_id.in_(frontier))
        if materialize_candidates:
            candidates = paths.cte("scope_candidates").prefix_with("MATERIALIZED")
            paths = select(candidates.c.descendant_id)
        remaining = config.library.max_scope_nodes - len(budget.nodes)
        rows = list(
            (
                await session.execute(
                    select(
                        Node,
                        case(
                            (
                                Node.type == NodeType.REFERENCE,
                                reference_visible(Node.__table__, viewer_id),
                            ),
                            else_=False,
                        ),
                    )
                    .where(
                        Node.id.in_(paths),
                        ~Node.id.in_(budget.nodes),
                        visible(Node.__table__, viewer_id),
                        or_(
                            Node.owner_id == viewer_id,
                            Node.type != NodeType.REFERENCE,
                            reference_visible(Node.__table__, viewer_id),
                        ),
                    )
                    .limit(remaining + 1)
                )
            ).all()
        )
        if len(rows) > remaining:
            raise Problem(422, "scope_too_large")
        decks = set()
        targets = set()
        for node, target_visible in rows:
            budget.nodes.add(node.id)
            budget.metadata[node.id] = node
            budget.types[node.id] = node.type
            if node.parent_id is not None:
                budget.edges.setdefault(node.parent_id, set()).add(node.id)
            if target_visible:
                budget.edges.setdefault(node.id, set()).add(node.reference_id)
                targets.add(node.reference_id)
            if node.type is NodeType.DECK:
                decks.add(node.id)
        if decks and include_memberships:
            # Limit before counting so an oversized remote deck never scans unbounded memberships.
            guard = (
                select(DeckSense.deck_id)
                .where(DeckSense.deck_id.in_(decks))
                .limit(config.library.max_scope_memberships - budget.memberships + 1)
                .subquery()
            )
            counts = (
                await session.execute(
                    select(guard.c.deck_id, func.count()).group_by(guard.c.deck_id)
                )
            ).all()
            budget.membership_counts.update(dict(counts))
            budget.memberships += sum(count for _, count in counts)
            if budget.memberships > config.library.max_scope_memberships:
                raise Problem(422, "scope_too_large")
            budget.decks.update(decks)
        frontier = targets - budget.nodes
    result = {}
    for root in roots:
        pending, visited = {root.id}, set()
        while pending:
            identifier = pending.pop()
            if identifier in visited or identifier not in budget.nodes:
                continue
            visited.add(identifier)
            pending.update(budget.edges.get(identifier, set()) - visited)
        result[root.id] = Scope(root, visited, visited & budget.decks)
    return result


async def scope_ids(session, node_id, viewer_id, config, *, budget=None):
    budget = budget or ScopeBudget(viewer_id)
    async with bounded(session, config, budget):
        scopes = await resolve_scopes(session, [node_id], viewer_id, config, budget=budget)
        return next(iter(scopes.values())).senses()
