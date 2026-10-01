"""Viewer-authorized, generation-safe folder statistics shared by API and agent tools."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pycil.library import analytics, scope
from pycil.library.access import ActorRef, require_node_access


async def get_folder_stats_for_viewer(
    session: AsyncSession, node_id: UUID, viewer_id: UUID
) -> analytics.FolderStats:
    """Authorize read access then calculate stats over the canonical subtree set."""
    await require_node_access(session, node_id, ActorRef(viewer_id), write=False)
    sense_ids = await scope.cached_sense_ids(session, node_id, viewer_id)
    return await analytics.stats_for_scope(session, viewer_id, sense_ids)
