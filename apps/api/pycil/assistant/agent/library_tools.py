"""Actor-aware collection operations for assistant tools.

The assistant never calls node-ID-only services directly. Every id entering
through a tool argument is resolved through the same ``require_node_access``
gate the HTTP routes use, so prompt-selected ids cannot reach another user's
nodes.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pycil.library import nodes, views
from pycil.library.access import ActorRef, require_node_access
from pycil.library.models import Node, NodeType, Visibility


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
    """One id-keyset page of the caller's own nodes under ``parent_id``.

    Delegates to ``views.owned_children_page`` so the assistant tool and the HTTP
    collection listing are two surfaces over ONE pagination scheme. The cursor is
    opaque, exactly like the route's: the owner predicate always applies, so a
    stale or foreign id can only shift where the caller's own scan resumes — it
    can never widen what is visible.
    """
    if parent_id is not None:
        await require_node_access(session, parent_id, ActorRef(actor_id), write=True)
    page, next_cursor = await views.owned_children_page(
        session, actor_id, parent_id, cursor=cursor, limit=limit
    )
    return {
        "items": [node_payload(node) for node in page],
        "next_cursor": next_cursor,
    }


async def get_node(session: AsyncSession, actor_id: UUID, node_id: UUID) -> dict:
    return node_payload(await require_node_access(session, node_id, ActorRef(actor_id), write=True))


async def create_folder(
    session: AsyncSession, actor_id: UUID, name: str, parent_id: UUID | None
) -> dict:
    if parent_id is not None:
        await require_node_access(session, parent_id, ActorRef(actor_id), write=True)
    node = await nodes.create_node(
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
        await require_node_access(session, parent_id, ActorRef(actor_id), write=True)
    node = await nodes.create_node(
        session,
        actor_id,
        node_type=NodeType.DECK,
        name=name,
        parent_node_id=parent_id,
    )
    return node_payload(node)


async def rename_node(session: AsyncSession, actor_id: UUID, node_id: UUID, name: str) -> dict:
    node = await require_node_access(session, node_id, ActorRef(actor_id), write=True)
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
    node = await require_node_access(session, node_id, ActorRef(actor_id), write=True)
    if parent_id is not None:
        await require_node_access(session, parent_id, ActorRef(actor_id), write=True)
    return node_payload(await nodes.move_node(session, node, parent_id, commit=commit))


async def set_private(session: AsyncSession, actor_id: UUID, node_id: UUID) -> dict:
    node = await require_node_access(session, node_id, ActorRef(actor_id), write=True)
    return node_payload(await nodes.set_visibility(session, node, Visibility.PRIVATE))


async def publish_node(
    session: AsyncSession, actor_id: UUID, node_id: UUID, *, commit: bool = True
) -> dict:
    node = await require_node_access(session, node_id, ActorRef(actor_id), write=True)
    return node_payload(
        await nodes.set_visibility(
            session, node, Visibility.PUBLIC, confirm_subtree_publication=True, commit=commit
        )
    )


async def delete_node(
    session: AsyncSession, actor_id: UUID, node_id: UUID, *, commit: bool = True
) -> None:
    await nodes.soft_delete_node(
        session,
        await require_node_access(session, node_id, ActorRef(actor_id), write=True),
        commit=commit,
    )
