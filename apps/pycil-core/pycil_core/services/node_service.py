"""Node service: CRUD for folders + decks. Owner-scoped (PRIVATE only in v1)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from shared.db.enums import NodeType as DbNodeType
from shared.db.models import DeckAttribute, FolderAttribute, Node, UserNode
from sqlalchemy import desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, select, update

from pycil_core.schemas.node import (
    BreadcrumbEntry,
    NodeCreate,
    NodeRead,
    NodeType,
    NodeUpdate,
)

_BREADCRUMB_DEPTH = 10


def _node_read_from_row(row) -> NodeRead:
    values = dict(row._mapping)
    values["is_starred"] = bool(values.get("is_starred"))
    values["is_pinned"] = bool(values.get("is_pinned"))
    return NodeRead(**values)


async def _breadcrumb(session: AsyncSession, node_id: UUID) -> list[BreadcrumbEntry]:
    """Recursive CTE walking parent_node_id. Capped at depth 10."""
    sql = text(
        """
        WITH RECURSIVE chain AS (
            SELECT id, parent_node_id, name, type, 0 AS depth
            FROM nodes WHERE id = :id
            UNION ALL
            SELECT n.id, n.parent_node_id, n.name, n.type, c.depth + 1
            FROM nodes n
            JOIN chain c ON n.id = c.parent_node_id
            WHERE c.depth < :max_depth
        )
        SELECT id, name, type FROM chain ORDER BY depth DESC
        """
    )
    rows = (await session.execute(sql, {"id": node_id, "max_depth": _BREADCRUMB_DEPTH})).all()
    return [BreadcrumbEntry(id=r.id, name=r.name, type=NodeType(r.type)) for r in rows]


async def _ensure_owner(session: AsyncSession, user_id: UUID, node_id: UUID) -> dict:
    """Fetch node and ensure user is the author. 404 if not found, 403 if not owner."""
    row = (await session.exec(select(Node).where(Node.id == node_id))).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "node_not_found")
    if row.author_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "node_forbidden")
    return row.model_dump()


async def list_root_nodes(session: AsyncSession, user_id: UUID) -> list[NodeRead]:
    stmt = (
        select(
            Node.id,
            Node.type,
            Node.name,
            Node.description,
            Node.parent_node_id,
            Node.target_node_id,
            Node.visibility,
            Node.definition_count,
            Node.created_at,
            Node.updated_at,
            UserNode.is_starred,
            UserNode.is_pinned,
        )
        .outerjoin(UserNode, (UserNode.node_id == Node.id) & (UserNode.user_id == user_id))
        .where(Node.author_id == user_id, col(Node.parent_node_id).is_(None))
        .order_by(desc(UserNode.is_pinned).nulls_last(), desc(Node.updated_at))
    )
    rows = (await session.exec(stmt)).all()
    return [_node_read_from_row(r) for r in rows]


async def list_children(session: AsyncSession, user_id: UUID, parent_id: UUID) -> list[NodeRead]:
    await _ensure_owner(session, user_id, parent_id)
    stmt = (
        select(
            Node.id,
            Node.type,
            Node.name,
            Node.description,
            Node.parent_node_id,
            Node.target_node_id,
            Node.visibility,
            Node.definition_count,
            Node.created_at,
            Node.updated_at,
            UserNode.is_starred,
            UserNode.is_pinned,
        )
        .outerjoin(UserNode, (UserNode.node_id == Node.id) & (UserNode.user_id == user_id))
        .where(Node.author_id == user_id, Node.parent_node_id == parent_id)
        .order_by(desc(UserNode.is_pinned).nulls_last(), desc(Node.updated_at))
    )
    rows = (await session.exec(stmt)).all()
    return [_node_read_from_row(r) for r in rows]


async def get_node(session: AsyncSession, user_id: UUID, node_id: UUID) -> NodeRead:
    row = await _ensure_owner(session, user_id, node_id)
    breadcrumb = await _breadcrumb(session, node_id)
    star_row = (
        await session.exec(
            select(UserNode).where(
                UserNode.user_id == user_id,
                UserNode.node_id == node_id,
            )
        )
    ).first()
    return NodeRead(
        id=row["id"],
        type=NodeType(row["type"]),
        name=row["name"],
        description=row["description"],
        parent_node_id=row["parent_node_id"],
        target_node_id=row["target_node_id"],
        visibility=row["visibility"],
        definition_count=row["definition_count"],
        is_starred=bool(star_row.is_starred) if star_row else False,
        is_pinned=bool(star_row.is_pinned) if star_row else False,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        breadcrumb=breadcrumb,
    )


async def create_node(session: AsyncSession, user_id: UUID, payload: NodeCreate) -> NodeRead:
    if payload.parent_node_id is not None:
        # Owner check on parent
        parent = await _ensure_owner(session, user_id, payload.parent_node_id)
        if parent["type"] != "FOLDER":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "parent_must_be_folder")

    target_node_id = None
    if payload.type == NodeType.SHORTCUT:
        # NodeCreate's validator guarantees target_node_id is set for SHORTCUT.
        target_node_id = payload.target_node_id
        assert target_node_id is not None
        # Validate the target exists and is owned by the caller before pointing a
        # shortcut at it — a shortcut must not grant access to a node the user
        # cannot already see. _ensure_owner 404s on missing, 403s on non-owner.
        await _ensure_owner(session, user_id, target_node_id)

    node = Node(
        author_id=user_id,
        type=DbNodeType(payload.type.value),
        parent_node_id=payload.parent_node_id,
        target_node_id=target_node_id,
        name=payload.name,
        description=payload.description,
    )
    session.add(node)
    await session.flush()
    if node.id is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "node_create_failed")
    if payload.type == NodeType.FOLDER:
        session.add(FolderAttribute(node_id=node.id))
        # Update parent's subfolder_count if parent is folder
        if payload.parent_node_id:
            await session.exec(
                update(FolderAttribute)
                .where(FolderAttribute.node_id == payload.parent_node_id)
                .values(subfolder_count=FolderAttribute.subfolder_count + 1)
            )
    elif payload.type == NodeType.DECK:
        session.add(DeckAttribute(node_id=node.id))
    # SHORTCUT carries no folder/deck attribute — it is a pure pointer row.
    await session.commit()
    return await get_node(session, user_id, node.id)


async def update_node(
    session: AsyncSession, user_id: UUID, node_id: UUID, payload: NodeUpdate
) -> NodeRead:
    await _ensure_owner(session, user_id, node_id)
    fields: dict = {}
    if payload.name is not None:
        fields["name"] = payload.name
    if payload.description is not None:
        fields["description"] = payload.description
    if not fields:
        return await get_node(session, user_id, node_id)
    await session.exec(
        update(Node).where(Node.id == node_id).values(**fields, updated_at=datetime.now(UTC))
    )
    await session.commit()
    return await get_node(session, user_id, node_id)


async def delete_node(session: AsyncSession, user_id: UUID, node_id: UUID) -> None:
    await _ensure_owner(session, user_id, node_id)
    await session.exec(delete(Node).where(Node.id == node_id))
    await session.commit()


async def admin_soft_delete_node(session: AsyncSession, node_id: UUID) -> bool:
    """Reversible admin soft-delete: set `deleted_at`, NO owner check, NO commit.

    Distinct from `delete_node` (a HARD owner-gated DELETE). Used by the reports
    moderation pipeline so a wrongly-deleted deck can be restored by nulling
    `deleted_at`. Caller owns the transaction (single commit with the audit row).
    Returns False if the node is gone or already soft-deleted.
    """
    result = await session.exec(
        update(Node)
        .where(Node.id == node_id, Node.deleted_at.is_(None))
        .values(deleted_at=datetime.now(UTC))
    )
    return bool(getattr(result, "rowcount", 0))


async def toggle_flag(
    session: AsyncSession, user_id: UUID, node_id: UUID, *, field: str
) -> NodeRead:
    if field not in {"is_starred", "is_pinned"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_flag")
    await _ensure_owner(session, user_id, node_id)
    sql = text(
        f"""
        INSERT INTO user_nodes (user_id, node_id, {field})
        VALUES (:uid, :nid, TRUE)
        ON CONFLICT (user_id, node_id) DO UPDATE
        SET {field} = NOT user_nodes.{field}, updated_at = NOW()
        """
    )
    await session.execute(sql, {"uid": user_id, "nid": node_id})
    await session.commit()
    return await get_node(session, user_id, node_id)
