"""Node ownership/visibility guard — the single IDOR gate for node routes.

Every node/deck route resolves access through ``require_node_access`` so a caller
can never touch a node they don't own (write) or can't see (read). Read allows
owner-or-public; write is owner-only. A missing node is a 404, not a 403, so the
guard doesn't leak existence of private nodes to non-owners.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ForbiddenError, NotFoundError
from pycil.hierarchy.models import Node, NodeType, Visibility


async def require_node_access(
    session: AsyncSession,
    node_id: UUID,
    user: CurrentUser | None,
    *,
    write: bool = False,
) -> Node:
    """Return the node if the user may access it, else raise.

    - write=True → owner-only (403 for anyone else).
    - write=False → owner, or anyone if the node is PUBLIC.
    - soft-deleted or unknown node → 404.
    """
    node = await session.get(Node, node_id)
    if node is None or node.deleted_at is not None:
        raise NotFoundError("node_not_found")

    is_owner = user is not None and node.author_id == user.id
    if write:
        if not is_owner:
            raise ForbiddenError("not_node_owner", code="forbidden")
    elif not await can_read_node(session, node, user.id if user is not None else None):
        # Don't leak private-node existence to non-owners.
        raise NotFoundError("node_not_found")
    return node


async def can_read_node(session: AsyncSession, node: Node, user_id: UUID | None) -> bool:
    """Whether a node is directly or inherited-public readable by ``user_id``."""
    if node.deleted_at is not None or not await _has_live_ancestry(session, node):
        return False
    if (user_id is not None and node.author_id == user_id) or node.visibility == Visibility.PUBLIC:
        return True

    # A public FOLDER grants inherited read access only through same-owner edges.
    current = node
    seen: set[UUID] = set()
    while current.parent_node_id is not None and current.id not in seen:
        if current.id is not None:
            seen.add(current.id)
        parent = await session.get(Node, current.parent_node_id)
        if parent is None or parent.deleted_at is not None:
            return False
        if parent.author_id != node.author_id:
            return False
        if parent.type == NodeType.FOLDER and parent.visibility == Visibility.PUBLIC:
            return True
        current = parent
    return False


async def _has_live_ancestry(session: AsyncSession, node: Node) -> bool:
    current = node
    seen: set[UUID] = set()
    while current.parent_node_id is not None and current.id not in seen:
        if current.id is not None:
            seen.add(current.id)
        parent = await session.get(Node, current.parent_node_id)
        if parent is None or parent.deleted_at is not None:
            return False
        current = parent
    return True
