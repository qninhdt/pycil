"""Thin server-authenticated tools, sharing HTTP business functions."""

from uuid import UUID

from langchain_core.tools import tool

from pycil.account.models import User
from pycil.library import nodes
from pycil.library.schemas import NodeCreate, NodeSave
from pycil.study.progress import progress


def tools(resources, user, config):
    @tool
    async def search_words(query: str):
        """Search saved Words and separately selectable reference entries."""
        from dataclasses import asdict

        return asdict(await resources.lexicon.search(query, include_available=True))

    @tool
    async def list_nodes(parent_id: str | None = None):
        """List Library roots or children of a readable folder/reference."""
        async with resources.sessions() as session:
            return await nodes.list_nodes(
                session, user.id, UUID(parent_id) if parent_id else None, None, config
            )

    @tool
    async def get_node(node_id: str):
        """Read authorized node metadata and breadcrumbs, not deck membership."""
        async with resources.sessions() as session:
            return await nodes.node_details(session, UUID(node_id), user.id, config)

    @tool
    async def get_node_editor(node_id: str):
        """Read owned editable metadata and complete deck sense_ids before a full save."""
        async with resources.sessions() as session:
            return await nodes.editor_snapshot(session, UUID(node_id), user.id, config)

    @tool
    async def create_node(data: dict):
        """Create a folder, deck or live reference. Publication requires approval."""
        value = NodeCreate.model_validate(data)
        async with resources.sessions() as session:
            return await nodes.create_node(session, user.id, value, config)

    @tool
    async def update_node(node_id: str, data: dict):
        """Save final metadata and deck sense_ids atomically; requires user approval."""
        value = NodeSave.model_validate(data)
        async with resources.sessions() as session:
            return await nodes.save_node(session, user.id, UUID(node_id), value, config)

    @tool
    async def delete_node(node_id: str):
        """Delete an owned normal subtree; requires user approval."""
        async with resources.sessions() as session:
            await nodes.delete_node(session, user.id, UUID(node_id), config)
        return {"deleted": True}

    @tool
    async def learning_progress(node_id: str | None = None):
        """Read current Sense progress, optionally scoped to a readable node."""
        async with resources.sessions() as session:
            current = await session.get(User, user.id)
            return await progress(session, current, config, UUID(node_id) if node_id else None)

    return [
        search_words,
        list_nodes,
        get_node,
        get_node_editor,
        create_node,
        update_node,
        delete_node,
        learning_progress,
    ]
