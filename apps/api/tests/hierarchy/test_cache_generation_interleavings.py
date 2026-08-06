"""Cache fills must not write a value from before a structural mutation."""

import pytest

from pycil.auth.models import User
from pycil.content.application import service as content_service
from pycil.hierarchy.application import cache, service, subtree
from pycil.hierarchy.infra.models import NodeType

pytestmark = pytest.mark.asyncio


async def test_cache_miss_retries_after_interleaved_membership_change(session, monkeypatch):
    owner = User(email="stale-fill-owner@example.com")
    session.add(owner)
    await session.commit()
    await session.refresh(owner)
    deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="stale-fill deck"
    )
    await content_service.add_sense(session, deck.id, 91)
    original_resolve = subtree.resolve_sense_ids
    first_call = True

    async def resolve_with_interleaved_write(current_session, node_id, viewer_id=None):
        nonlocal first_call
        if first_call:
            first_call = False
            stale_sense_ids = await original_resolve(
                current_session, node_id, viewer_id
            )
            await content_service.add_sense(current_session, deck.id, 92)
            return stale_sense_ids
        return await original_resolve(current_session, node_id, viewer_id)

    monkeypatch.setattr(subtree, "resolve_sense_ids", resolve_with_interleaved_write)

    assert await subtree.cached_sense_ids(session, deck.id, owner.id) == [91, 92]
    await session.refresh(deck)
    cached = await cache.get_defset(
        deck.id, deck.structural_generation, viewer_id=owner.id
    )
    assert cached == [91, 92]
