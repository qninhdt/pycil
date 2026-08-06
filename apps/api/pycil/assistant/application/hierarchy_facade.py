"""Actor-aware hierarchy operations for assistant tools.

The assistant never calls node-ID-only services directly. This facade repeats
ownership checks at the application boundary so prompt-selected IDs are safe.
"""

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.errors import NotFoundError
from pycil.hierarchy.application import service
from pycil.hierarchy.infra.models import Node, NodeType, Visibility


async def _owned_node(session: AsyncSession, actor_id: UUID, node_id: UUID) -> Node:
    node = await session.get(Node, node_id)
    if node is None or node.deleted_at is not None or node.author_id != actor_id:
        raise NotFoundError("node_not_found")
    return node


def node_payload(node: Node) -> dict:
    return {
        "id": str(node.id),
        "type": node.type.value,
        "name": node.name,
        "parent_id": str(node.parent_node_id) if node.parent_node_id else None,
        "visibility": node.visibility.value,
        "generation": node.structural_generation,
    }


async def list_nodes(
    session: AsyncSession,
    actor_id: UUID,
    parent_id: UUID | None,
    limit: int,
    cursor: UUID | None = None,
) -> dict:
    if parent_id is not None:
        await _owned_node(session, actor_id, parent_id)
    conditions = [
        Node.author_id == actor_id,
        Node.parent_node_id == parent_id,
        Node.deleted_at.is_(None),
    ]
    if cursor is not None:
        cursor_node = await _owned_node(session, actor_id, cursor)
        if cursor_node.parent_node_id != parent_id:
            raise NotFoundError("assistant_cursor_not_in_collection")
        conditions.append(
            or_(
                Node.created_at > cursor_node.created_at,
                and_(Node.created_at == cursor_node.created_at, Node.id > cursor_node.id),
            )
        )
    rows = list(
        await session.scalars(
            select(Node).where(*conditions).order_by(Node.created_at, Node.id).limit(limit + 1)
        )
    )
    page, extra = rows[:limit], rows[limit:]
    return {
        "items": [node_payload(node) for node in page],
        "next_cursor": str(page[-1].id) if extra and page else None,
    }


async def get_node(session: AsyncSession, actor_id: UUID, node_id: UUID) -> dict:
    return node_payload(await _owned_node(session, actor_id, node_id))


async def create_folder(
    session: AsyncSession, actor_id: UUID, name: str, parent_id: UUID | None
) -> dict:
    if parent_id is not None:
        await _owned_node(session, actor_id, parent_id)
    node = await service.create_node(
        session,
        actor_id,
        node_type=NodeType.FOLDER,
        name=name,
        parent_node_id=parent_id,
        visibility=Visibility.PRIVATE,
    )
    return node_payload(node)


async def create_deck(
    session: AsyncSession, actor_id: UUID, name: str, parent_id: UUID | None
) -> dict:
    if parent_id is not None:
        await _owned_node(session, actor_id, parent_id)
    node = await service.create_node(
        session,
        actor_id,
        node_type=NodeType.DECK,
        name=name,
        parent_node_id=parent_id,
    )
    return node_payload(node)


async def rename_node(session: AsyncSession, actor_id: UUID, node_id: UUID, name: str) -> dict:
    node = await _owned_node(session, actor_id, node_id)
    node.name = name
    await session.commit()
    await session.refresh(node)
    return node_payload(node)


async def move_node(
    session: AsyncSession,
    actor_id: UUID,
    node_id: UUID,
    parent_id: UUID | None,
    *,
    commit: bool = True,
) -> dict:
    node = await _owned_node(session, actor_id, node_id)
    if parent_id is not None:
        await _owned_node(session, actor_id, parent_id)
    return node_payload(await service.move_node(session, node, parent_id, commit=commit))


async def set_private(session: AsyncSession, actor_id: UUID, node_id: UUID) -> dict:
    node = await _owned_node(session, actor_id, node_id)
    return node_payload(await service.set_visibility(session, node, Visibility.PRIVATE))


async def publish_node(
    session: AsyncSession, actor_id: UUID, node_id: UUID, *, commit: bool = True
) -> dict:
    node = await _owned_node(session, actor_id, node_id)
    return node_payload(
        await service.set_visibility(
            session, node, Visibility.PUBLIC, confirm_subtree_publication=True, commit=commit
        )
    )


async def delete_node(
    session: AsyncSession, actor_id: UUID, node_id: UUID, *, commit: bool = True
) -> None:
    await service.soft_delete_node(
        session, await _owned_node(session, actor_id, node_id), commit=commit
    )
