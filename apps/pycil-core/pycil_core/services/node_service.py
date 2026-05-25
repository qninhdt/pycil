"""Node service: CRUD for folders + decks. Owner-scoped (PRIVATE only in v1)."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.schemas.node import (
    BreadcrumbEntry,
    NodeCreate,
    NodeRead,
    NodeType,
    NodeUpdate,
)

_BREADCRUMB_DEPTH = 10


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
    sql = text(
        """
        SELECT id, author_id, type, name, description, parent_node_id, visibility,
               definition_count, created_at, updated_at
        FROM nodes WHERE id = :id
        """
    )
    row = (await session.execute(sql, {"id": node_id})).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "node_not_found")
    if row.author_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "node_forbidden")
    return dict(row._mapping)


async def list_root_nodes(session: AsyncSession, user_id: UUID) -> list[NodeRead]:
    sql = text(
        """
        SELECT n.id, n.type, n.name, n.description, n.parent_node_id,
               n.visibility::text AS visibility, n.definition_count,
               n.created_at, n.updated_at,
               COALESCE(un.is_starred, FALSE) AS is_starred,
               COALESCE(un.is_pinned, FALSE) AS is_pinned
        FROM nodes n
        LEFT JOIN user_nodes un ON un.node_id = n.id AND un.user_id = :uid
        WHERE n.author_id = :uid AND n.parent_node_id IS NULL
        ORDER BY un.is_pinned DESC NULLS LAST, n.updated_at DESC
        """
    )
    rows = (await session.execute(sql, {"uid": user_id})).all()
    return [NodeRead(**dict(r._mapping)) for r in rows]


async def list_children(
    session: AsyncSession, user_id: UUID, parent_id: UUID
) -> list[NodeRead]:
    await _ensure_owner(session, user_id, parent_id)
    sql = text(
        """
        SELECT n.id, n.type, n.name, n.description, n.parent_node_id,
               n.visibility::text AS visibility, n.definition_count,
               n.created_at, n.updated_at,
               COALESCE(un.is_starred, FALSE) AS is_starred,
               COALESCE(un.is_pinned, FALSE) AS is_pinned
        FROM nodes n
        LEFT JOIN user_nodes un ON un.node_id = n.id AND un.user_id = :uid
        WHERE n.author_id = :uid AND n.parent_node_id = :pid
        ORDER BY un.is_pinned DESC NULLS LAST, n.updated_at DESC
        """
    )
    rows = (await session.execute(sql, {"uid": user_id, "pid": parent_id})).all()
    return [NodeRead(**dict(r._mapping)) for r in rows]


async def get_node(
    session: AsyncSession, user_id: UUID, node_id: UUID
) -> NodeRead:
    row = await _ensure_owner(session, user_id, node_id)
    breadcrumb = await _breadcrumb(session, node_id)
    star_sql = text(
        "SELECT is_starred, is_pinned FROM user_nodes "
        "WHERE user_id = :uid AND node_id = :nid"
    )
    star_row = (
        await session.execute(star_sql, {"uid": user_id, "nid": node_id})
    ).first()
    return NodeRead(
        id=row["id"],
        type=NodeType(row["type"]),
        name=row["name"],
        description=row["description"],
        parent_node_id=row["parent_node_id"],
        visibility=row["visibility"],
        definition_count=row["definition_count"],
        is_starred=bool(star_row.is_starred) if star_row else False,
        is_pinned=bool(star_row.is_pinned) if star_row else False,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        breadcrumb=breadcrumb,
    )


async def create_node(
    session: AsyncSession, user_id: UUID, payload: NodeCreate
) -> NodeRead:
    if payload.parent_node_id is not None:
        # Owner check on parent
        parent = await _ensure_owner(session, user_id, payload.parent_node_id)
        if parent["type"] != "FOLDER":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "parent_must_be_folder"
            )

    insert_sql = text(
        """
        INSERT INTO nodes (author_id, type, parent_node_id, name, description)
        VALUES (:uid, :type, :pid, :name, :desc)
        RETURNING id, created_at, updated_at
        """
    )
    row = (
        await session.execute(
            insert_sql,
            {
                "uid": user_id,
                "type": payload.type.value,
                "pid": payload.parent_node_id,
                "name": payload.name,
                "desc": payload.description,
            },
        )
    ).one()
    if payload.type == NodeType.FOLDER:
        await session.execute(
            text("INSERT INTO folder_attributes (node_id) VALUES (:id)"),
            {"id": row.id},
        )
        # Update parent's subfolder_count if parent is folder
        if payload.parent_node_id:
            await session.execute(
                text(
                    "UPDATE folder_attributes SET subfolder_count = subfolder_count + 1 "
                    "WHERE node_id = :id"
                ),
                {"id": payload.parent_node_id},
            )
    else:
        await session.execute(
            text("INSERT INTO deck_attributes (node_id) VALUES (:id)"),
            {"id": row.id},
        )
    await session.commit()
    return await get_node(session, user_id, row.id)


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
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = node_id
    await session.execute(
        text(f"UPDATE nodes SET {set_clause}, updated_at = NOW() WHERE id = :id"),
        fields,
    )
    await session.commit()
    return await get_node(session, user_id, node_id)


async def delete_node(
    session: AsyncSession, user_id: UUID, node_id: UUID
) -> None:
    await _ensure_owner(session, user_id, node_id)
    await session.execute(text("DELETE FROM nodes WHERE id = :id"), {"id": node_id})
    await session.commit()


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
