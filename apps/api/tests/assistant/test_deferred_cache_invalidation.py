"""An approved assistant mutation invalidates the cache its write superseded.

A tool that runs under human approval must not commit on its own: the domain write
and the action result belong in one transaction, so `_run_sensitive` passes
``commit=False`` and commits both together. But the cache cleanup has to follow
that commit, and the deferred branch used to bump the structural generation and
return without recording anything — so an approved "remove this word" left the
superseded definition set in Redis for the full hour of the cache TTL.

Correctness never depended on Redis (the generation is part of every key, so a
bumped generation makes the old value unreachable), which is exactly why the leak
was invisible: nothing was ever served stale, the keys simply accumulated at
nodes x viewers x mutations.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from pycil.assistant.application import tools as assistant_tools
from pycil.assistant.application.hitl import create_pending_action
from pycil.assistant.domain.context import AssistantContext
from pycil.assistant.infra.models import ActionStatus
from pycil.content.application import service as content_service
from pycil.hierarchy.application import cache
from pycil.hierarchy.application import service as hierarchy_service
from pycil.hierarchy.infra.models import NodeType

from .conftest import create_run, create_thread, create_user

pytestmark = pytest.mark.asyncio


async def _executing_action(session, owner_id, tool: str, arguments: dict):
    """A HITL action in the state `_run_sensitive` requires to execute."""
    thread = await create_thread(session, owner_id)
    run = await create_run(session, thread.id, owner_id, uuid4())
    action = await create_pending_action(
        session,
        run_id=run.id,
        owner_id=owner_id,
        tool=tool,
        arguments=arguments,
        checkpoint_version=f"run:{run.id}",
    )
    action.status = ActionStatus.EXECUTING
    await session.commit()
    return action


def _runtime(owner, action_id):
    class Runtime:
        context = AssistantContext(owner.id, owner.token_version, action_id)

    return Runtime()


async def test_an_approved_sense_removal_deletes_the_cache_it_superseded(
    engine, session, monkeypatch, fake_redis
):
    owner = await create_user(session)
    deck = await hierarchy_service.create_node(
        session, author_id=owner.id, node_type=NodeType.DECK, name="Deck"
    )
    await content_service.add_sense(session, deck.id, 4242)

    # Populate the cache at the deck's current generation, the way a read would.
    generation = await cache.current_generation(session, deck.id)
    assert generation is not None
    await cache.set_defset(deck.id, [4242], generation=generation, viewer_id=owner.id)
    cached_key = f"node:{deck.id}:defset:v{generation}:viewer:{owner.id}"
    assert await fake_redis.get(cached_key) is not None

    action = await _executing_action(
        session, owner.id, "remove_sense_from_deck", {"deck_id": str(deck.id)}
    )
    monkeypatch.setattr(
        assistant_tools,
        "async_session_factory",
        async_sessionmaker(engine, expire_on_commit=False),
    )

    async def operation(inner_session, commit: bool) -> str:
        assert commit is False, "an approved action must not commit its own write"
        await content_service.remove_sense(inner_session, deck.id, 4242, commit=commit)
        return "removed"

    result = await assistant_tools._run_sensitive(_runtime(owner, action.id), operation)

    assert result == "removed"
    assert await fake_redis.get(cached_key) is None, (
        "the superseded definition set must be deleted once the action commits"
    )


async def test_the_invalidation_runs_after_the_commit_not_before(
    engine, session, monkeypatch, fake_redis
):
    """Ordering is the invariant, not just the end state.

    Deleting before the commit leaves a window where a concurrent reader still sees
    the pre-commit generation, repopulates the key it just removed, and the stale
    value outlives the mutation again. A test asserting only "key is absent" would
    pass against that.
    """
    owner = await create_user(session)
    deck = await hierarchy_service.create_node(
        session, author_id=owner.id, node_type=NodeType.DECK, name="Ordered"
    )
    await content_service.add_sense(session, deck.id, 77)
    action = await _executing_action(
        session, owner.id, "remove_sense_from_deck", {"deck_id": str(deck.id)}
    )

    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(assistant_tools, "async_session_factory", factory)

    order: list[str] = []
    real_flush = cache.flush_deferred_invalidations

    async def tracked_flush(tracked_session):
        order.append("invalidate")
        await real_flush(tracked_session)

    monkeypatch.setattr(cache, "flush_deferred_invalidations", tracked_flush)

    async def operation(inner_session, commit: bool) -> str:
        await content_service.remove_sense(inner_session, deck.id, 77, commit=commit)

        original_commit = inner_session.commit

        async def recording_commit():
            order.append("commit")
            await original_commit()

        monkeypatch.setattr(inner_session, "commit", recording_commit)
        return "removed"

    await assistant_tools._run_sensitive(_runtime(owner, action.id), operation)

    assert order == ["commit", "invalidate"]


async def test_an_approved_publish_invalidates_the_hierarchy_cache(
    engine, session, monkeypatch, fake_redis
):
    """The same deferred branch exists on the hierarchy side, with the same bug."""
    owner = await create_user(session)
    folder = await hierarchy_service.create_node(
        session, author_id=owner.id, node_type=NodeType.FOLDER, name="Folder"
    )

    generation = await cache.current_generation(session, folder.id)
    assert generation is not None
    await cache.set_defset(folder.id, [1, 2], generation=generation, viewer_id=owner.id)
    cached_key = f"node:{folder.id}:defset:v{generation}:viewer:{owner.id}"
    assert await fake_redis.get(cached_key) is not None

    action = await _executing_action(
        session, owner.id, "publish_node", {"node_id": str(folder.id)}
    )
    monkeypatch.setattr(
        assistant_tools,
        "async_session_factory",
        async_sessionmaker(engine, expire_on_commit=False),
    )

    async def operation(inner_session, commit: bool):
        node = await inner_session.get(type(folder), folder.id)
        await hierarchy_service.set_visibility(
            inner_session,
            node,
            visibility=folder.visibility.__class__.PUBLIC,
            confirm_subtree_publication=True,
            commit=commit,
        )
        return "published"

    await assistant_tools._run_sensitive(_runtime(owner, action.id), operation)

    assert await fake_redis.get(cached_key) is None
