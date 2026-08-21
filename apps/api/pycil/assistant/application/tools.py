"""The complete bounded tool surface for the assistant agent."""

from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any
from uuid import UUID, uuid4

from langchain.tools import ToolRuntime, tool

from pycil.assistant.application import content_facade, hierarchy_facade
from pycil.assistant.application.persistence import revalidate_actor
from pycil.assistant.domain.context import AssistantContext
from pycil.assistant.infra.models import ActionStatus, AssistantAction, AssistantActionAudit
from pycil.common.errors import AppError, TooManyRequestsError
from pycil.config import settings
from pycil.content.application import generation_quota
from pycil.db.redis import get_arq_pool, get_redis
from pycil.db.session import async_session_factory
from pycil.hierarchy.application import cache
from pycil.hierarchy.application.viewer_stats import get_folder_stats_for_viewer
from pycil.ports.lexi_provider import get_lexi_client
from pycil.tasks.application import service as task_service
from pycil.tasks.domain.vocabulary import JOB_NAME_FOR_KIND, TASK_KIND_WORD, WordDispatch
from pycil.tasks.domain.work_keys import word_work_key

MAX_RESULTS = 50

# Mirrors the HTTP route's ``WordRequest.query`` bound so both producers reject
# the same input rather than one of them truncating it.
MAX_QUERY_LENGTH = 200


async def _mutate(runtime: ToolRuntime[AssistantContext]) -> None:
    async with async_session_factory() as session:
        await revalidate_actor(session, runtime.context.user_id, runtime.context.token_version)


async def _run_sensitive(
    runtime: ToolRuntime[AssistantContext], operation: Callable[[Any, bool], Awaitable[Any]]
) -> Any:
    """Commit the domain write and action result in one database transaction."""
    async with async_session_factory() as session:
        await revalidate_actor(session, runtime.context.user_id, runtime.context.token_version)
        action_id = runtime.context.action_id
        if action_id is None:
            return await operation(session, True)
        action = await session.get(AssistantAction, action_id, with_for_update=True)
        if action is None or action.owner_id != runtime.context.user_id:
            raise RuntimeError("assistant_action_not_found")
        if action.status == ActionStatus.SUCCEEDED:
            return (action.result or {}).get("tool_result")
        if action.status != ActionStatus.EXECUTING:
            raise RuntimeError("assistant_action_not_executing")
        result = await operation(session, False)
        action.status = ActionStatus.SUCCEEDED
        action.result = {"tool_result": result}
        session.add(
            AssistantActionAudit(
                action_id=action.id,
                actor_id=action.owner_id,
                decision="succeeded",
                sanitized_digest=action.args_digest,
                correlation_id=action.correlation_id,
            )
        )
        await session.commit()
        # The domain write deferred its cache cleanup to whoever owns the commit,
        # which is here. Running it before the commit would let a concurrent reader
        # repopulate the key from the pre-commit generation.
        await cache.flush_deferred_invalidations(session)
        return result


@tool
async def list_nodes(
    parent_id: UUID | None,
    limit: int,
    runtime: ToolRuntime[AssistantContext],
    cursor: UUID | None = None,
) -> dict:
    """List one capped page of the caller's child nodes; pass next_cursor to continue."""
    async with async_session_factory() as session:
        return await hierarchy_facade.list_nodes(
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
        return await hierarchy_facade.get_node(session, runtime.context.user_id, node_id)


@tool
async def create_folder(
    name: str, parent_id: UUID | None, runtime: ToolRuntime[AssistantContext]
) -> dict:
    """Create a private folder for the caller."""
    await _mutate(runtime)
    async with async_session_factory() as session:
        return await hierarchy_facade.create_folder(
            session, runtime.context.user_id, name[:200], parent_id
        )


@tool
async def create_deck(
    name: str, parent_id: UUID | None, runtime: ToolRuntime[AssistantContext]
) -> dict:
    """Create a private deck for the caller."""
    await _mutate(runtime)
    async with async_session_factory() as session:
        return await hierarchy_facade.create_deck(
            session, runtime.context.user_id, name[:200], parent_id
        )


@tool
async def rename_node(node_id: UUID, name: str, runtime: ToolRuntime[AssistantContext]) -> dict:
    """Rename a caller-owned node."""
    await _mutate(runtime)
    async with async_session_factory() as session:
        return await hierarchy_facade.rename_node(
            session, runtime.context.user_id, node_id, name[:200]
        )


@tool
async def make_node_private(node_id: UUID, runtime: ToolRuntime[AssistantContext]) -> dict:
    """Make a caller-owned node private."""
    await _mutate(runtime)
    async with async_session_factory() as session:
        return await hierarchy_facade.set_private(session, runtime.context.user_id, node_id)


@tool
async def move_node(
    node_id: UUID, parent_id: UUID | None, runtime: ToolRuntime[AssistantContext]
) -> dict:
    """Move a caller-owned node. Human approval is required before execution."""
    return await _run_sensitive(
        runtime,
        lambda session, commit: hierarchy_facade.move_node(
            session, runtime.context.user_id, node_id, parent_id, commit=commit
        ),
    )


@tool
async def publish_node(node_id: UUID, runtime: ToolRuntime[AssistantContext]) -> dict:
    """Publish a node and potentially expose descendants. Human approval is required."""
    return await _run_sensitive(
        runtime,
        lambda session, commit: hierarchy_facade.publish_node(
            session, runtime.context.user_id, node_id, commit=commit
        ),
    )


@tool
async def delete_node(node_id: UUID, runtime: ToolRuntime[AssistantContext]) -> str:
    """Delete a caller-owned node. Human approval is required before execution."""

    async def operation(session, commit: bool) -> str:
        await hierarchy_facade.delete_node(session, runtime.context.user_id, node_id, commit=commit)
        return "deleted"

    return await _run_sensitive(runtime, operation)


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
        return await content_facade.list_deck_items(
            session,
            runtime.context.user_id,
            deck_id,
            min(max(limit, 1), MAX_RESULTS),
            cursor,
        )


@tool
async def request_word_generation(query: str, runtime: ToolRuntime[AssistantContext]) -> str:
    """Queue vocabulary generation for the caller."""
    await _mutate(runtime)
    # The HTTP route rejects an over-long query at the boundary. Silently slicing
    # here would generate an entry for a word the caller did not ask for.
    trimmed = query.strip()
    if not trimmed or len(trimmed) > MAX_QUERY_LENGTH:
        raise AppError(
            "word_generation_query_invalid",
            code="word_generation_query_invalid",
        )
    owner_id = runtime.context.user_id
    redis = get_redis()
    if not await generation_quota.reserve_quota(redis, owner_id):
        raise TooManyRequestsError(
            "word_generation_quota_exceeded",
            code="word_generation_quota_exceeded",
            retry_after=3600,
        )
    dispatch = WordDispatch(query=trimmed, owner_id=str(owner_id))
    async with async_session_factory() as session:
        try:
            submission = await task_service.submit_or_join(
                session,
                kind=TASK_KIND_WORD,
                server_work_key=word_work_key(
                    generation_quota.normalize_query(trimmed),
                    settings.lexi_reference_dataset_fingerprint,
                ),
                requester_id=owner_id,
                command_kind="word.generate",
                command_id=f"word:{uuid4()}",
                provenance="assistant",
                dispatch=dispatch,
            )
        except Exception:
            await generation_quota.release_inflight_quota(redis, owner_id)
            raise
    if not submission.task_created:
        await generation_quota.release_inflight_quota(redis, owner_id)
    else:
        try:
            await (await get_arq_pool()).enqueue_job(
                JOB_NAME_FOR_KIND[TASK_KIND_WORD],
                str(submission.task.id),
                *dispatch.job_args(),
            )
        except Exception:
            # The durable reconciler will enqueue this committed task.
            pass
    return f"generation_requested:{submission.task.id}"


@tool
async def add_sense_to_deck(
    deck_id: UUID, sense_id: int, runtime: ToolRuntime[AssistantContext]
) -> dict:
    """Add a dictionary sense to a caller-owned deck."""
    await _mutate(runtime)
    async with async_session_factory() as session:
        return await content_facade.add_sense(session, runtime.context.user_id, deck_id, sense_id)


@tool
async def remove_sense_from_deck(
    deck_id: UUID, sense_id: int, runtime: ToolRuntime[AssistantContext]
) -> str:
    """Remove a sense from a deck. Human approval is required before execution."""

    async def operation(session, commit: bool) -> str:
        await content_facade.remove_sense(
            session, runtime.context.user_id, deck_id, sense_id, commit=commit
        )
        return "removed"

    return await _run_sensitive(runtime, operation)


@tool
async def folder_stats(node_id: UUID, runtime: ToolRuntime[AssistantContext]) -> dict:
    """Return study statistics for a caller-owned folder or deck."""
    async with async_session_factory() as session:
        await hierarchy_facade.get_node(session, runtime.context.user_id, node_id)
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
    make_node_private,
    move_node,
    publish_node,
    delete_node,
    search_word,
    list_deck_items,
    request_word_generation,
    add_sense_to_deck,
    remove_sense_from_deck,
    folder_stats,
]
