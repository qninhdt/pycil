from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, and_, bindparam, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.library.access import reference_visible, visible
from pycil.library.config import LibraryConfig
from pycil.library.models import Node, NodeRole, NodeSpace, NodeType
from pycil.library.nodes import decode, encode, includes, page_limit
from pycil.library.scope import ScopeBudget, bounded, resolve_scopes
from pycil.library.types import NodePageDict
from pycil.study.config import StudyConfig
from pycil.utils.errors import InvalidInput
from pycil.utils.orm import row_data

# Reuse expression trees, not authorization results; each request supplies its viewer.
_VIEWER = bindparam("viewer_id", type_=Node.__table__.c.owner_id.type)
_VISIBLE_VIEWER = bindparam("visible_viewer_id", type_=Node.__table__.c.owner_id.type)
_AUTHORIZED_CANDIDATES = select(Node).where(
    visible(Node.__table__, _VISIBLE_VIEWER),
    or_(
        and_(bindparam("scoped", type_=Boolean), Node.owner_id == _VIEWER),
        Node.type != NodeType.REFERENCE,
        reference_visible(Node.__table__, _VIEWER),
    ),
)
_READABLE_PARENTS = select(Node.id).where(visible(Node.__table__, _VIEWER))


async def search_nodes(
    session: AsyncSession,
    viewer_id: UUID | None,
    config: LibraryConfig,
    *,
    node_id: UUID | None = None,
    q: str | None = None,
    type: NodeType | None = None,
    owner_id: UUID | None = None,
    cursor: str | None = None,
    limit: int | None = None,
    include: str | None = None,
    budget: ScopeBudget | None = None,
    study_config: StudyConfig | None = None,
) -> NodePageDict:
    limit = page_limit(limit, config)
    enrichment = includes(include, {"summary"})
    if q is not None:
        if not q.strip() or len(q) > config.max_query_chars:
            raise InvalidInput("invalid_query")
        q = q.strip()
    if node_id is not None and q is None:
        raise InvalidInput("query_required")
    binding = {
        "kind": "node_search" if node_id else "discovery",
        "viewer": str(viewer_id),
        "scope": str(node_id),
        "q": q,
        "type": str(type),
        "owner": str(owner_id),
    }
    seek, _ = decode(cursor, binding, ["rank", "uuid"] if q else ["time", "uuid"])
    budget = budget or ScopeBudget(viewer_id)
    async with bounded(session, config, budget):
        rank = (
            func.ts_rank_cd(Node.search_vector, func.websearch_to_tsquery("simple", q))
            if q
            else Node.created_at
        )
        query = select(Node.id, rank.label("rank")).where(Node.deleted_at.is_(None))
        if node_id is not None:
            scope = next(
                iter(
                    (
                        await resolve_scopes(
                            session,
                            [node_id],
                            viewer_id,
                            config,
                            budget=budget,
                            include_memberships="summary" in enrichment,
                            materialize_candidates=True,
                        )
                    ).values()
                )
            )
            if scope.root.type is NodeType.DECK:
                raise InvalidInput("invalid_search_scope")
            query = query.where(Node.id.in_(scope.nodes))
        else:
            query = query.where(
                Node.role == NodeRole.NORMAL,
                Node.space == NodeSpace.PUBLISHED,
            )
        if type is not None:
            query = query.where(Node.type == type)
        if owner_id is not None:
            query = query.where(Node.owner_id == owner_id)
        if q:
            query = query.where(Node.search_vector.op("@@")(func.websearch_to_tsquery("simple", q)))
            ordering = [rank.desc(), Node.id]
        else:
            ordering = [Node.created_at.desc(), Node.id.desc()]
        rows: list[tuple[Node, float | datetime]] = []
        batch_size = max(50, 2 * (limit + 1))
        candidate_seek = seek
        while len(rows) <= limit:
            batch_query = query
            if candidate_seek:
                if q:
                    batch_query = batch_query.where(
                        or_(
                            rank < candidate_seek[0],
                            and_(rank == candidate_seek[0], Node.id > candidate_seek[1]),
                        )
                    )
                else:
                    batch_query = batch_query.where(
                        tuple_(Node.created_at, Node.id) < tuple_(*candidate_seek)
                    )
            candidates = list(
                (await session.execute(batch_query.order_by(*ordering).limit(batch_size))).all()
            )
            if not candidates:
                break
            candidate_ids = [identifier for identifier, _ in candidates]
            candidate_filter = Node.id.in_(candidate_ids)
            if node_id is not None:
                ids = (
                    select(Node.id)
                    .where(Node.id.in_(candidate_ids))
                    .cte("search_candidates")
                    .prefix_with("MATERIALIZED")
                )
                candidate_filter = Node.id.in_(select(ids.c.id))
            authorized_rows = await session.scalars(
                _AUTHORIZED_CANDIDATES.where(candidate_filter),
                {
                    "viewer_id": viewer_id,
                    "visible_viewer_id": viewer_id if node_id is not None else None,
                    "scoped": node_id is not None,
                },
            )
            authorized = {node.id: node for node in authorized_rows}
            rows.extend(
                (authorized[identifier], value)
                for identifier, value in candidates
                if identifier in authorized
            )
            if len(candidates) < batch_size:
                break
            last_id, last_rank = candidates[-1]
            candidate_seek = (last_rank, last_id)
        page = rows[:limit]
        items: list[dict[str, object]] = [row_data(row[0]) for row in page]
        parents: set[UUID] = {row[0].parent_id for row in page if row[0].parent_id is not None}
        readable_parents: set[UUID] = (
            set(
                (
                    await session.scalars(
                        _READABLE_PARENTS.where(Node.id.in_(parents)),
                        {"viewer_id": viewer_id},
                    )
                ).all()
            )
            if parents
            else set()
        )
        for item in items:
            if item["parent_id"] not in readable_parents:
                item["parent_id"] = None
        if "summary" in enrichment and page:
            if study_config is None:
                raise InvalidInput("study_config_required")
            from pycil.study.progress import summaries

            counts = await summaries(
                session,
                viewer_id,
                study_config,
                [r[0].id for r in page],
                library_config=config,
                budget=budget,
            )
            for item, summary in zip(items, counts, strict=True):
                item["summary"] = summary
        return {
            "nodes": items,
            "next_cursor": (
                encode(binding, [page[-1][1], page[-1][0].id]) if len(rows) > limit else None
            ),
        }
