"""Subtree resolution + folder stats + CEFR bucketing + REFERENCE rules."""

from types import SimpleNamespace

import pytest

from pycil.account.user import User
from pycil.library import analytics as stats
from pycil.library import nodes as service
from pycil.library import scope as subtree
from pycil.library.models import DeckSense, NodeType
from pycil.study.models import SenseStatus
from pycil.study.models import UserSenseStats as USS

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

    ids = await subtree.resolve_sense_ids(session, root.id, owner.id)
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
    # The viewer is explicit: a reference target is authorized on its own merits,
    # and target_deck is private, so only the owner reaches it. Passing no viewer
    # means ANONYMOUS here, not "skip the check".
    ids = await subtree.resolve_sense_ids(session, root.id, owner.id)
    assert sorted(ids) == [10, 11]
    assert await subtree.resolve_sense_ids(session, root.id, None) == []


async def test_reference_to_a_folder_contributes_its_whole_readable_subtree(session):
    """A folder target is a share of a whole section, not just one list.

    The alternative — refusing a folder target — would leave the feature the product
    advertises (share a folder, let someone study all of it) with no way to express it.
    """
    owner = await _user(session)
    source = await service.create_node(session, owner.id, node_type=NodeType.FOLDER, name="src")
    inner = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="inner", parent_node_id=source.id
    )
    deck_a = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="a", parent_node_id=source.id
    )
    deck_b = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="b", parent_node_id=inner.id
    )
    await _add_senses(session, deck_a.id, [1, 2])
    await _add_senses(session, deck_b.id, [2, 3])

    root = await service.create_node(session, owner.id, node_type=NodeType.FOLDER, name="root")
    await service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="ref to folder",
        parent_node_id=root.id,
        target_node_id=source.id,
    )

    ids = await subtree.resolve_sense_ids(session, root.id, owner.id)

    # Both decks, de-duplicated: sense 2 is in each.
    assert sorted(ids) == [1, 2, 3]


async def test_a_reference_to_an_unreadable_folder_contributes_nothing(session):
    """The target authorizes independently of the folder holding the reference.

    Otherwise publishing the containing folder would launder a private target's
    content into it.
    """
    owner = await _user(session)
    stranger = await _user(session, "stranger@example.com")
    private_source = await service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="private src"
    )
    deck = await service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="d", parent_node_id=private_source.id
    )
    await _add_senses(session, deck.id, [7])

    root = await service.create_node(session, owner.id, node_type=NodeType.FOLDER, name="root")
    await service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="ref",
        parent_node_id=root.id,
        target_node_id=private_source.id,
    )

    assert await subtree.resolve_sense_ids(session, root.id, stranger.id) == []
    assert sorted(await subtree.resolve_sense_ids(session, root.id, owner.id)) == [7]


async def test_a_reference_to_a_reference_is_refused(session):
    """An indirection the resolver cannot bound is refused at creation."""
    from pycil.platform.errors import ConflictError

    owner = await _user(session)
    deck = await service.create_node(session, owner.id, node_type=NodeType.DECK, name="d")
    first = await service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="first",
        target_node_id=deck.id,
    )
    with pytest.raises(ConflictError) as exc:
        await service.create_node(
            session,
            owner.id,
            node_type=NodeType.REFERENCE,
            name="second",
            target_node_id=first.id,
        )
    assert exc.value.code == "reference_must_target_deck_or_folder"


async def test_folder_stats_learned_mastered_avg(session):
    owner = await _user(session)
    deck = await service.create_node(session, owner.id, node_type=NodeType.DECK, name="d")
    await _add_senses(session, deck.id, [1, 2, 3, 4])
    # 3 learned; masteries 90, 50, 10; sense 4 never studied.
    for sid, m in [(1, 90), (2, 50), (3, 10)]:
        session.add(
            USS(
                user_id=owner.id,
                sense_id=sid,
                mastery=m,
                review_count=1,
                stability=float(m),
                status=SenseStatus.scheduled,
            )
        )
    await session.commit()

    ids = await subtree.resolve_sense_ids(session, deck.id, owner.id)
    s = await stats.stats_for_scope(session, owner.id, ids, mastered_threshold=80)
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
            USS(
                user_id=owner.id,
                sense_id=sid,
                mastery=m,
                review_count=1,
                stability=float(m),
                status=SenseStatus.scheduled,
            )
        )
    await session.commit()
    ids = await subtree.resolve_sense_ids(session, deck.id, owner.id)
    weak = await stats.weakest_senses(session, owner.id, ids, limit=2)
    assert [w.sense_id for w in weak] == [2, 3]  # lowest mastery first


async def test_weakest_senses_excludes_unlearned_rows(session):
    owner = await _user(session)
    deck = await service.create_node(session, owner.id, node_type=NodeType.DECK, name="d")
    await _add_senses(session, deck.id, [1, 2])
    session.add(USS(user_id=owner.id, sense_id=1, mastery=0, review_count=0))
    session.add(
        USS(
            user_id=owner.id,
            sense_id=2,
            mastery=20,
            review_count=1,
            status=SenseStatus.scheduled,
        )
    )
    await session.commit()

    weak = await stats.weakest_senses(
        session, owner.id, await subtree.resolve_sense_ids(session, deck.id, owner.id)
    )
    assert [item.sense_id for item in weak] == [2]


async def test_cefr_distribution_via_client_not_join(session):
    client = FakeLexiClient({1: "A1", 2: "A1", 3: "B2", 4: None})
    dist = await stats.cefr_distribution(client, [1, 2, 3, 4])
    assert dist == {"A1": 2, "B2": 1, "unknown": 1}


async def test_folder_stats_empty_set(session):
    owner = await _user(session)
    s = await stats.stats_for_scope(session, owner.id, [])
    assert s == stats.FolderStats(total=0, learned=0, mastered=0, avg_mastery=0.0)
