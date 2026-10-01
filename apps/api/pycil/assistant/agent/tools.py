"""The complete bounded tool surface for the assistant agent.

Exactly the accepted tool set, no more: an extra model-visible tool is a
capability the product did not agree to expose, and a missing one is a request
the assistant cannot serve. Batch add and remove are single tools taking a list,
because "add these five words" is one user action and N individual calls would
make it N transactions and N approvals.
"""

from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any
from uuid import UUID

from langchain.tools import ToolRuntime, tool

from pycil.assistant.agent import lexicon_tools, library_tools
from pycil.assistant.agent.context import AssistantContext
from pycil.assistant.thread_access import revalidate_actor
from pycil.lexicon.provider import get_lexi_client
from pycil.library.viewer_analytics import get_folder_stats_for_viewer
from pycil.platform.database import async_session_factory

MAX_RESULTS = 50

#: One batch call is still bounded. A caller asking to add 10,000 senses is a
#: mistake or an abuse, and the refusal should arrive before the transaction.
MAX_SENSES_PER_BATCH = 200


async def _run_sensitive(
    runtime: ToolRuntime[AssistantContext], operation: Callable[[Any, bool], Awaitable[Any]]
) -> Any:
    """Re-check the actor and ownership inside every approved write.

    The approval was granted against state read earlier; re-validating here is
    what stops a pending approval from acting on an account or a node that has
    since changed.
    """
    async with async_session_factory() as session:
        await revalidate_actor(session, runtime.context.user_id)
        return await operation(session, True)


def _bounded_sense_ids(sense_ids: list[int]) -> list[int]:
    if not sense_ids:
        raise ValueError("sense_ids_required")
    if len(sense_ids) > MAX_SENSES_PER_BATCH:
        raise ValueError("sense_ids_too_many")
    return sense_ids


@tool
async def list_nodes(
    parent_id: UUID | None,
    limit: int,
    runtime: ToolRuntime[AssistantContext],
    cursor: UUID | None = None,
) -> dict:
    """List one capped page of the caller's child nodes; pass next_cursor to continue."""
    async with async_session_factory() as session:
        return await library_tools.list_nodes(
            session,
            runtime.context.user_id,
            parent_id,
            min(max(limit, 1), MAX_RESULTS),
            cursor,
        )


@tool
async def get_node(node_id: UUID, runtime: ToolRuntime[AssistantContext]) -> dict:
    """Get one caller-owned folder, deck, or reference node."""
    async with async_session_factory() as session:
        return await library_tools.get_node(session, runtime.context.user_id, node_id)


@tool
async def create_folder(
    name: str, parent_id: UUID | None, runtime: ToolRuntime[AssistantContext]
) -> dict:
    """Create a private folder for the caller."""
    async with async_session_factory() as session:
        await revalidate_actor(session, runtime.context.user_id)
        return await library_tools.create_folder(
            session, runtime.context.user_id, name[:200], parent_id
        )


@tool
async def create_deck(
    name: str, parent_id: UUID | None, runtime: ToolRuntime[AssistantContext]
) -> dict:
    """Create a private deck for the caller."""
    async with async_session_factory() as session:
        await revalidate_actor(session, runtime.context.user_id)
        return await library_tools.create_deck(
            session, runtime.context.user_id, name[:200], parent_id
        )


@tool
async def rename_node(node_id: UUID, name: str, runtime: ToolRuntime[AssistantContext]) -> dict:
    """Rename a caller-owned node."""
    async with async_session_factory() as session:
        await revalidate_actor(session, runtime.context.user_id)
        return await library_tools.rename_node(
            session, runtime.context.user_id, node_id, name[:200]
        )


@tool
async def move_node(
    node_id: UUID, parent_id: UUID | None, runtime: ToolRuntime[AssistantContext]
) -> dict:
    """Move a caller-owned node. Human approval is required before execution."""
    return await _run_sensitive(
        runtime,
        lambda session, commit: library_tools.move_node(
            session, runtime.context.user_id, node_id, parent_id, commit=commit
        ),
    )


@tool
async def delete_node(node_id: UUID, runtime: ToolRuntime[AssistantContext]) -> str:
    """Delete a caller-owned node. Human approval is required before execution."""

    async def operation(session, commit: bool) -> str:
        await library_tools.delete_node(session, runtime.context.user_id, node_id, commit=commit)
        return "deleted"

    return await _run_sensitive(runtime, operation)


@tool
async def publish_node(node_id: UUID, runtime: ToolRuntime[AssistantContext]) -> dict:
    """Publish a node and potentially expose descendants. Human approval is required."""
    return await _run_sensitive(
        runtime,
        lambda session, commit: library_tools.publish_node(
            session, runtime.context.user_id, node_id, commit=commit
        ),
    )


@tool
async def make_node_private(node_id: UUID, runtime: ToolRuntime[AssistantContext]) -> dict:
    """Make a caller-owned node private. Revokes publication immediately."""
    async with async_session_factory() as session:
        await revalidate_actor(session, runtime.context.user_id)
        return await library_tools.set_private(session, runtime.context.user_id, node_id)


@tool
async def search_word(query: str, runtime: ToolRuntime[AssistantContext]) -> list[dict]:
    """Search the dictionary for a word; results are limited."""
    del runtime
    results = await get_lexi_client().search(query[:200])
    return [asdict(result) for result in results[:MAX_RESULTS]]


@tool
async def list_deck_items(
    deck_id: UUID,
    limit: int,
    runtime: ToolRuntime[AssistantContext],
    cursor: int | None = None,
) -> dict:
    """List one capped page of content in a caller-owned deck; pass next_cursor to continue."""
    async with async_session_factory() as session:
        return await lexicon_tools.list_deck_items(
            session,
            runtime.context.user_id,
            deck_id,
            min(max(limit, 1), MAX_RESULTS),
            cursor,
        )


@tool
async def add_senses_to_deck(
    deck_id: UUID, sense_ids: list[int], runtime: ToolRuntime[AssistantContext]
) -> dict:
    """Add one or more dictionary senses to a caller-owned deck in a single call."""
    async with async_session_factory() as session:
        await revalidate_actor(session, runtime.context.user_id)
        return await lexicon_tools.add_senses(
            session, runtime.context.user_id, deck_id, _bounded_sense_ids(sense_ids)
        )


@tool
async def remove_senses_from_deck(
    deck_id: UUID, sense_ids: list[int], runtime: ToolRuntime[AssistantContext]
) -> dict:
    """Remove one or more senses from a deck. Human approval is required."""

    async def operation(session, commit: bool) -> dict:
        return await lexicon_tools.remove_senses(
            session,
            runtime.context.user_id,
            deck_id,
            _bounded_sense_ids(sense_ids),
            commit=commit,
        )

    return await _run_sensitive(runtime, operation)


@tool
async def folder_stats(node_id: UUID, runtime: ToolRuntime[AssistantContext]) -> dict:
    """Return study statistics for a caller-owned folder or deck."""
    async with async_session_factory() as session:
        await library_tools.get_node(session, runtime.context.user_id, node_id)
        result = await get_folder_stats_for_viewer(session, node_id, runtime.context.user_id)
    return {
        "total": result.total,
        "learned": result.learned,
        "mastered": result.mastered,
        "avg_mastery": result.avg_mastery,
    }


ALL_TOOLS = [
    list_nodes,
    get_node,
    create_folder,
    create_deck,
    rename_node,
    move_node,
    delete_node,
    publish_node,
    make_node_private,
    search_word,
    list_deck_items,
    add_senses_to_deck,
    remove_senses_from_deck,
    folder_stats,
]
