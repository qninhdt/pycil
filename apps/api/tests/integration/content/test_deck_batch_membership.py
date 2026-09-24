"""Batch deck membership is one transaction, not one per sense.

The assistant exposes add/remove as a single tool taking a list, so the property
that matters is that N senses cost one deck-content-generation bump and one
commit — and that a request naming a sense twice does not double-insert it.
"""

import pytest
from sqlalchemy import func, select

from pycil.auth.models import User
from pycil.content.application import service
from pycil.content.infra.models import DeckSense

pytestmark = pytest.mark.asyncio


async def _owner(session, email: str = "batch-owner@x.co") -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _deck(session, owner: User, name: str = "Batch Deck"):
    return await service.create_deck(session, owner.id, name)


async def _generation(session, deck_id) -> int:
    from pycil.hierarchy.infra.models import Node

    node = await session.get(Node, deck_id)
    await session.refresh(node)
    return node.content_generation


async def _membership_count(session, deck_id) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(DeckSense)
                .where(DeckSense.node_id == deck_id)
            )
        ).scalar_one()
    )


async def test_many_senses_are_added_in_one_commit_with_one_generation_bump(session):
    owner = await _owner(session)
    deck = await _deck(session, owner)
    before = await _generation(session, deck.id)

    added = await service.add_senses(session, deck.id, [101, 202, 303, 404, 505])

    assert [row.sense_id for row in added] == [101, 202, 303, 404, 505]
    assert await service.list_sense_ids(session, deck.id) == [101, 202, 303, 404, 505]
    # One edit, one cache invalidation: N bumps would make deck content
    # generation meaningless as a change marker.
    assert await _generation(session, deck.id) == before + 1


async def test_a_repeated_sense_in_one_batch_is_added_once(session):
    owner = await _owner(session)
    deck = await _deck(session, owner)

    added = await service.add_senses(session, deck.id, [7, 7, 8, 7])

    assert [row.sense_id for row in added] == [7, 8]
    assert await _membership_count(session, deck.id) == 2


async def test_a_sense_already_in_the_deck_is_not_duplicated_by_a_batch(session):
    owner = await _owner(session)
    deck = await _deck(session, owner)
    await service.add_sense(session, deck.id, 11)

    added = await service.add_senses(session, deck.id, [11, 12])

    assert [row.sense_id for row in added] == [12]
    assert await _membership_count(session, deck.id) == 2


async def test_an_empty_batch_is_a_no_op_without_a_generation_bump(session):
    owner = await _owner(session)
    deck = await _deck(session, owner)
    before = await _generation(session, deck.id)

    assert await service.add_senses(session, deck.id, []) == []
    assert await _generation(session, deck.id) == before


async def test_removing_many_senses_reports_the_count_and_keeps_the_rest(session):
    owner = await _owner(session)
    deck = await _deck(session, owner)
    await service.add_senses(session, deck.id, [1, 2, 3, 4, 5])

    removed = await service.remove_senses(session, deck.id, [2, 4, 99])

    assert removed == 2
    assert await service.list_sense_ids(session, deck.id) == [1, 3, 5]


async def test_removing_nothing_bumps_no_generation(session):
    owner = await _owner(session)
    deck = await _deck(session, owner)
    await service.add_senses(session, deck.id, [1])
    before = await _generation(session, deck.id)

    assert await service.remove_senses(session, deck.id, []) == 0
    assert await _generation(session, deck.id) == before
