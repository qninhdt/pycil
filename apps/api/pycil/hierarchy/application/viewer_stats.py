"""Viewer-authorized, generation-safe folder statistics shared by API and agent tools."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.errors import NotFoundError
from pycil.hierarchy.application import stats, subtree
from pycil.hierarchy.application.access import can_read_node
from pycil.hierarchy.infra.models import Node


async def get_folder_stats_for_viewer(
    session: AsyncSession, node_id: UUID, viewer_id: UUID
) -> stats.FolderStats:
    """Authorize read access then calculate stats over the canonical subtree set."""
    node = await session.get(Node, node_id)
    if node is None or not await can_read_node(session, node, viewer_id):
        raise NotFoundError("node_not_found")
    sense_ids = await subtree.cached_sense_ids(session, node_id, viewer_id)
    return await stats.folder_stats(session, viewer_id, sense_ids)
