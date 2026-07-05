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
from pycil.hierarchy.models import Node, Visibility


async def require_node_access(
    session: AsyncSession,
    node_id: UUID,
    user: CurrentUser,
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

    is_owner = node.author_id == user.id
    if write:
        if not is_owner:
            raise ForbiddenError("not_node_owner", code="forbidden")
    else:
        if not is_owner and node.visibility != Visibility.PUBLIC:
            # Don't leak private-node existence to non-owners.
            raise NotFoundError("node_not_found")
    return node
