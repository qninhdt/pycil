"""Live authorization from physical system-root paths, never display names."""

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement
from sqlalchemy.sql.selectable import Exists, FromClause

from pycil.library.models import Node, NodePath, NodeRole, NodeType
from pycil.utils.errors import NotFound


def has_root(node: FromClause, role: NodeRole) -> Exists:
    root = Node.__table__.alias()
    path = NodePath.__table__.alias()
    return (
        select(path.c.ancestor_id)
        .join(root, root.c.id == path.c.ancestor_id)
        .where(
            path.c.descendant_id == node.c.id,
            root.c.owner_id == node.c.owner_id,
            root.c.role == role,
            root.c.type == NodeType.FOLDER,
            root.c.deleted_at.is_(None),
        )
        .correlate(node)
        .exists()
    )


def published(node: FromClause) -> ColumnElement[bool]:
    return and_(has_root(node, NodeRole.LIBRARY_ROOT), has_root(node, NodeRole.PUBLISHED_ROOT))


def visible(node: FromClause, viewer_id: UUID | None) -> ColumnElement[bool]:
    ancestor = Node.__table__.alias()
    path = NodePath.__table__.alias()
    broken = (
        select(path.c.ancestor_id)
        .join(ancestor, ancestor.c.id == path.c.ancestor_id)
        .where(path.c.descendant_id == node.c.id, ancestor.c.deleted_at.is_not(None))
        .correlate(node)
        .exists()
    )
    return and_(
        node.c.deleted_at.is_(None),
        ~broken,
        has_root(node, NodeRole.LIBRARY_ROOT),
        or_(
            node.c.owner_id == viewer_id if viewer_id is not None else False,
            has_root(node, NodeRole.PUBLISHED_ROOT),
        ),
    )


def reference_visible(node: FromClause, viewer_id: UUID | None) -> Exists:
    target = Node.__table__.alias()
    return (
        select(target.c.id)
        .where(
            target.c.id == node.c.reference_id,
            target.c.type.in_([NodeType.FOLDER, NodeType.DECK]),
            visible(target, viewer_id),
            or_(~has_root(node, NodeRole.PUBLISHED_ROOT), published(target)),
        )
        .correlate(node)
        .exists()
    )


async def readable(session: AsyncSession, node_id: UUID, viewer_id: UUID | None) -> Node:
    node = await session.scalar(
        select(Node).where(Node.id == node_id, visible(Node.__table__, viewer_id))
    )
    if node is None:
        raise NotFound("node_not_found")
    if node.type is NodeType.REFERENCE and node.owner_id != viewer_id:
        available = await session.scalar(
            select(reference_visible(Node.__table__, viewer_id)).where(Node.id == node_id)
        )
        if not available:
            raise NotFound("node_not_found")
    return node


async def readable_path(
    session: AsyncSession, node_id: UUID, viewer_id: UUID | None
) -> tuple[Node, list[Node]]:
    node = await readable(session, node_id, viewer_id)
    ancestors = list(
        (
            await session.scalars(
                select(Node)
                .join(NodePath, NodePath.ancestor_id == Node.id)
                .where(NodePath.descendant_id == node.id)
                .order_by(NodePath.depth.desc())
            )
        ).all()
    )
    if node.owner_id != viewer_id:
        start = next(
            (i for i, n in enumerate(ancestors) if n.role is NodeRole.PUBLISHED_ROOT), None
        )
        ancestors = ancestors[start:] if start is not None else []
    return node, ancestors
