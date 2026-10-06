"""Thin server-authenticated tools, sharing HTTP business functions."""

from uuid import UUID

from langchain_core.tools import tool

from pycil.account.models import User
from pycil.library import nodes
from pycil.library.schemas import NodeCreate, NodeSave
from pycil.library.search import search_nodes as search_service
from pycil.study.progress import progress
from pycil.vocabulary.context import SenseIDs, viewer_context


def tools(resources, user, config):
    @tool
    async def search_words(query: str):
        """Search saved Words and separately selectable reference entries."""
        from dataclasses import asdict

        return asdict(await resources.lexicon.search(query, include_available=True))

    @tool
    async def list_nodes(
        parent_id: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
        include: str | None = None,
    ):
        """List Library roots or children of a readable folder/reference."""
        async with resources.sessions() as session:
            return await nodes.list_nodes(
                session,
                user.id,
                UUID(parent_id) if parent_id else None,
                cursor,
                config,
                limit=limit,
                include=include,
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
        """Read exact new/studied/due counts and applied-review recency, not history or mastery."""
        async with resources.sessions() as session:
            current = await session.get(User, user.id)
            return await progress(session, current, config, UUID(node_id) if node_id else None)

    @tool
    async def search_nodes(
        query: str | None = None,
        node_id: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
        include: str | None = None,
    ):
        """Search a readable Library/folder scope, or browse/search public Discovery."""
        async with resources.sessions() as session:
            return await search_service(
                session,
                user.id,
                config,
                q=query,
                node_id=UUID(node_id) if node_id else None,
                cursor=cursor,
                limit=limit,
                include=include,
            )

    @tool
    async def sense_context(sense_ids: list[int]):
        """Read personal state and readable Library decks for up to 100 distinct senses."""
        data = SenseIDs(sense_ids=sense_ids)
        async with resources.sessions() as session:
            return await viewer_context(session, user.id, config, data.sense_ids)

    return [
        search_words,
        list_nodes,
        get_node,
        get_node_editor,
        create_node,
        update_node,
        delete_node,
        learning_progress,
        search_nodes,
        sense_context,
    ]
