"""Subtree resolution + folder stats + CEFR bucketing + REFERENCE rules."""

from types import SimpleNamespace

import pytest

from pycil.auth.models import User
from pycil.content.models import DeckSense
from pycil.hierarchy import service, stats, subtree
from pycil.hierarchy.models import NodeType
from pycil.learning.models import UserSenseStats as USS

pytestmark = pytest.mark.asyncio


class FakeLexiClient:
    """Serves canned SenseViews with CEFR levels for bucketing tests."""

    def __init__(self, cefr_by_id: dict[int, str]):
        self._cefr = cefr_by_id

    async def get_senses(self, sense_ids):
        return [
            SimpleNamespace(
                definition=f"d{sid}",
                tier="core",
                pos="noun",
                cefr_level=self._cefr.get(sid),
                sense_id=sid,
            )
            for sid in sense_ids
        ]


async def _user(session, email="owner@x.co") -> User:
    u = User(email=email)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _add_senses(session, node_id, sense_ids):
    for pos, sid in enumerate(sense_ids):
        session.add(DeckSense(node_id=node_id, sense_id=sid, position=pos))
    await session.commit()


async def test_subtree_resolves_nested_folders(session):
    owner = await _user(session)
    root = await service.create_node(session, owner.id, node_type=NodeType.FOLDER, name="root")
    sub = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="sub", parent_node_id=root.id
    )
    deck1 = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="d1", parent_node_id=root.id
    )
    deck2 = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="d2", parent_node_id=sub.id
    )
    await _add_senses(session, deck1.id, [1, 2, 3])
    await _add_senses(session, deck2.id, [3, 4])  # 3 overlaps → DISTINCT

    ids = await subtree.resolve_sense_ids(session, root.id)
    assert sorted(ids) == [1, 2, 3, 4]


async def test_reference_expands_to_target_deck(session):
    owner = await _user(session)
    root = await service.create_node(session, owner.id, node_type=NodeType.FOLDER, name="root")
    target_deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="target"
    )
    await _add_senses(session, target_deck.id, [10, 11])
    # A REFERENCE under root pointing at target_deck contributes its senses.
    await service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="ref",
        parent_node_id=root.id,
        target_node_id=target_deck.id,
    )
    ids = await subtree.resolve_sense_ids(session, root.id)
    assert sorted(ids) == [10, 11]


async def test_reference_must_target_deck_not_folder(session):
    from pycil.common.errors import ConflictError

    owner = await _user(session)
    folder = await service.create_node(session, owner.id, node_type=NodeType.FOLDER, name="f")
    with pytest.raises(ConflictError):
        await service.create_node(
            session,
            owner.id,
            node_type=NodeType.REFERENCE,
            name="bad-ref",
            target_node_id=folder.id,  # folder, not deck → rejected
        )


async def test_folder_stats_learned_mastered_avg(session):
    owner = await _user(session)
    deck = await service.create_node(session, owner.id, node_type=NodeType.DECK, name="d")
    await _add_senses(session, deck.id, [1, 2, 3, 4])
    # 3 learned; masteries 90, 50, 10; sense 4 never studied.
    for sid, m in [(1, 90), (2, 50), (3, 10)]:
        session.add(
            USS(user_id=owner.id, sense_id=sid, mastery=m, review_count=1, stability=float(m))
        )
    await session.commit()

    ids = await subtree.resolve_sense_ids(session, deck.id)
    s = await stats.folder_stats(session, owner.id, ids, mastered_threshold=80)
    assert s.total == 4
    assert s.learned == 3
    assert s.mastered == 1  # only mastery 90 >= 80
    assert s.avg_mastery == 50.0  # (90+50+10)/3


async def test_weakest_senses_orders_by_mastery_asc(session):
    owner = await _user(session)
    deck = await service.create_node(session, owner.id, node_type=NodeType.DECK, name="d")
    await _add_senses(session, deck.id, [1, 2, 3])
    for sid, m in [(1, 90), (2, 20), (3, 55)]:
        session.add(
            USS(user_id=owner.id, sense_id=sid, mastery=m, review_count=1, stability=float(m))
        )
    await session.commit()
    ids = await subtree.resolve_sense_ids(session, deck.id)
    weak = await stats.weakest_senses(session, owner.id, ids, limit=2)
    assert [w.sense_id for w in weak] == [2, 3]  # lowest mastery first


async def test_weakest_senses_excludes_unlearned_rows(session):
    owner = await _user(session)
    deck = await service.create_node(session, owner.id, node_type=NodeType.DECK, name="d")
    await _add_senses(session, deck.id, [1, 2])
    session.add(USS(user_id=owner.id, sense_id=1, mastery=0, review_count=0))
    session.add(USS(user_id=owner.id, sense_id=2, mastery=20, review_count=1))
    await session.commit()

    weak = await stats.weakest_senses(
        session, owner.id, await subtree.resolve_sense_ids(session, deck.id)
    )
    assert [item.sense_id for item in weak] == [2]


async def test_cefr_distribution_via_client_not_join(session):
    client = FakeLexiClient({1: "A1", 2: "A1", 3: "B2", 4: None})
    dist = await stats.cefr_distribution(client, [1, 2, 3, 4])
    assert dist == {"A1": 2, "B2": 1, "unknown": 1}


async def test_folder_stats_empty_set(session):
    owner = await _user(session)
    s = await stats.folder_stats(session, owner.id, [])
    assert s == stats.FolderStats(total=0, learned=0, mastered=0, avg_mastery=0.0)
