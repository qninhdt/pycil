"""Viewer-authorized, generation-safe folder statistics shared by API and agent tools."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.errors import NotFoundError
from pycil.hierarchy import cache, stats, subtree
from pycil.hierarchy.access import can_read_node
from pycil.hierarchy.models import Node


async def _defset(session: AsyncSession, node_id: UUID, viewer_id: UUID) -> list[int]:
    """Read a generation-safe, viewer-scoped canonical subtree sense set."""
    for _ in range(2):
        generation = await cache.current_generation(session, node_id)
        if generation is None:
            return []
        try:
            cached = await cache.get_defset(node_id, generation, viewer_id=viewer_id)
        except Exception:
            cached = None
        if cached is not None:
            return cached
        sense_ids = await subtree.resolve_sense_ids(session, node_id, viewer_id)
        if await cache.current_generation(session, node_id) == generation:
            try:
                await cache.set_defset(
                    node_id, sense_ids, generation=generation, viewer_id=viewer_id
                )
            except Exception:
                pass
            return sense_ids
    return await subtree.resolve_sense_ids(session, node_id, viewer_id)


async def get_folder_stats_for_viewer(
    session: AsyncSession, node_id: UUID, viewer_id: UUID
) -> stats.FolderStats:
    """Authorize read access then calculate stats over the canonical subtree set."""
    node = await session.get(Node, node_id)
    if node is None or not await can_read_node(session, node, viewer_id):
        raise NotFoundError("node_not_found")
    return await stats.folder_stats(session, viewer_id, await _defset(session, node_id, viewer_id))
