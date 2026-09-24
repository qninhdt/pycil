"""A cache fill must not publish membership the database has already moved past.

The race this guards: a read resolves a deck's membership, a concurrent edit adds a
sense and bumps the generation, and the read then writes its now-stale result. Under
the old subtree cache that would publish a stale set under a *fresh* key, making it
permanently reachable. Under the per-deck design the danger is narrower — the write
is keyed by the generation that was current when the read began — so the test
asserts the outcome a reader actually sees: the added sense is visible, and no key
carries a set that contradicts the database.
"""

import pytest

from pycil.auth.models import User
from pycil.content.application import service as content_service
from pycil.db.redis import get_redis
from pycil.hierarchy.application import cache, service, subtree
from pycil.hierarchy.infra.models import NodeType

pytestmark = pytest.mark.asyncio


async def test_a_read_racing_a_membership_change_still_returns_the_new_sense(
    session, monkeypatch
):
    owner = User(email="stale-fill-owner@example.com")
    session.add(owner)
    await session.commit()
    await session.refresh(owner)
    deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="stale-fill deck"
    )
    await content_service.add_sense(session, deck.id, 91)

    original = subtree.resolve_deck_ids
    injected = False

    async def resolve_with_interleaved_write(current_session, node_id, viewer_id=None):
        """Add a sense between the deck set being resolved and membership read."""
        nonlocal injected
        deck_ids = await original(current_session, node_id, viewer_id)
        if not injected:
            injected = True
            await content_service.add_sense(current_session, deck.id, 92)
        return deck_ids

    monkeypatch.setattr(subtree, "resolve_deck_ids", resolve_with_interleaved_write)

    resolved = await subtree.cached_sense_ids(session, deck.id, owner.id)

    # The interleaved write committed, so the read must reflect it. Whichever
    # generation it landed on, the answer cannot omit a committed sense.
    assert 92 in resolved, "a committed membership change must be visible"
    assert sorted(resolved) == [91, 92]

    # And whatever was cached is keyed by the generation it was read at, so a later
    # read composes the current membership rather than trusting a stale entry.
    await session.refresh(deck)
    redis = get_redis()
    cached_now = await cache.get_deck_senses(redis, deck.id, deck.content_generation)
    if cached_now is not None:
        assert sorted(cached_now) == [91, 92], (
            "the key carrying the current generation must hold the current membership"
        )
    assert await subtree.cached_sense_ids(session, deck.id, owner.id) == [91, 92]
