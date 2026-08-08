"""/me/history, /me/cefr, /me/weakest — the global scope Progress needs.

These existed only as /folders/{id}/... variants. The global scope is deliberately
NOT a client-side fan-out over roots: a sense held in two decks would be counted
twice, which is the same reason resolve_sense_ids uses SELECT DISTINCT. Aggregating
over the caller's user_sense_stats rows is unique per sense by primary key, and it
skips subtree resolution entirely, so it is cheaper than the folder path rather than
a sum of it.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ConflictError
from pycil.content.application import service as content_service
from pycil.hierarchy.application import reads
from pycil.hierarchy.application import service as hierarchy_service
from pycil.hierarchy.infra.models import NodeType
from pycil.hierarchy.router import (
    global_cefr,
    global_history,
    global_stats,
    global_weakest,
)
from pycil.learning.infra.models import ReviewLog, SenseStatus, UserSenseStats

pytestmark = pytest.mark.asyncio


class FakeLexiReader:
    """Content for the senses under test; unknown ids are simply absent."""

    def __init__(self, senses: dict[int, tuple[str, str | None]]):
        self._senses = senses

    async def get_senses(self, sense_ids):
        return [
            SimpleNamespace(
                sense_id=sense_id,
                definition=f"definition of {self._senses[sense_id][0]}",
                tier="core",
                pos="noun",
                cefr_level=self._senses[sense_id][1],
                word=self._senses[sense_id][0],
                word_id=sense_id * 10,
                examples=[],
            )
            for sense_id in sense_ids
            if sense_id in self._senses
        ]


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _cu(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, email=user.email)


async def _stat(session, user_id, sense_id, mastery, *, review_count=1):
    session.add(
        UserSenseStats(
            user_id=user_id,
            sense_id=sense_id,
            mastery=mastery,
            review_count=review_count,
            status=SenseStatus.scheduled,
        )
    )
    await session.commit()


# --- weakest ----------------------------------------------------------------


async def test_global_weakest_is_renderable_and_ordered(session):
    owner = await _user(session, "gw-owner@example.com")
    await _stat(session, owner.id, 1, 90)
    await _stat(session, owner.id, 2, 12)
    await _stat(session, owner.id, 3, 45)
    reader = FakeLexiReader({1: ("alpha", "A1"), 2: ("beta", "B2"), 3: ("gamma", None)})

    rows = await global_weakest(_cu(owner), session, reader, limit=10)

    assert [row.sense_id for row in rows] == [2, 3, 1]
    # A progress bar with no label is useless; every row carries its word.
    assert [row.word for row in rows] == ["beta", "gamma", "alpha"]
    assert rows[0].mastery == 12
    assert rows[0].cefr_level == "B2"
    assert rows[0].definition == "definition of beta"
    assert rows[1].cefr_level is None


async def test_weakest_keeps_a_row_whose_content_vanished_from_lexi(session):
    owner = await _user(session, "gw-missing@example.com")
    await _stat(session, owner.id, 99, 5)
    reader = FakeLexiReader({})

    rows = await global_weakest(_cu(owner), session, reader, limit=10)

    assert [row.sense_id for row in rows] == [99]
    assert rows[0].mastery == 5
    assert rows[0].word is None


async def test_weakest_is_scoped_to_the_caller(session):
    owner = await _user(session, "gw-mine@example.com")
    other = await _user(session, "gw-theirs@example.com")
    await _stat(session, owner.id, 1, 50)
    await _stat(session, other.id, 2, 1)
    reader = FakeLexiReader({1: ("mine", "A1"), 2: ("theirs", "A1")})

    rows = await global_weakest(_cu(owner), session, reader, limit=10)

    assert [row.sense_id for row in rows] == [1]


# --- cefr -------------------------------------------------------------------


async def test_global_cefr_buckets_every_tracked_sense(session):
    owner = await _user(session, "gc-owner@example.com")
    await _stat(session, owner.id, 1, 10)
    await _stat(session, owner.id, 2, 20)
    await _stat(session, owner.id, 3, 30)
    reader = FakeLexiReader({1: ("a", "A1"), 2: ("b", "A1"), 3: ("c", None)})

    assert await global_cefr(_cu(owner), session, reader) == {"A1": 2, "unknown": 1}


async def test_a_sense_in_two_decks_is_counted_once(session):
    """The double-count a client-side fan-out over roots would produce."""
    owner = await _user(session, "gc-dup@example.com")
    first = await hierarchy_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="first"
    )
    second = await hierarchy_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="second"
    )
    await content_service.add_sense(session, first.id, 7)
    await content_service.add_sense(session, second.id, 7)
    await _stat(session, owner.id, 7, 40)
    reader = FakeLexiReader({7: ("shared", "B1")})

    assert await global_cefr(_cu(owner), session, reader) == {"B1": 1}


# --- history ----------------------------------------------------------------


async def test_global_history_buckets_by_day(session):
    owner = await _user(session, "gh-owner@example.com")
    await _stat(session, owner.id, 1, 50)
    today = datetime.now(UTC)
    session.add(
        ReviewLog(
            user_id=owner.id,
            sense_id=1,
            stability_before=0.0,
            stability_after=1.0,
            mastery_before=0,
            mastery_after=50,
            grade=3,
            reviewed_at=today,
        )
    )
    await session.commit()

    buckets = await global_history(
        _cu(owner), session, from_date=today.date() - timedelta(days=2), to_date=today.date()
    )

    assert [item.bucket for item in buckets] == [
        (today.date() - timedelta(days=2)).isoformat(),
        (today.date() - timedelta(days=1)).isoformat(),
        today.date().isoformat(),
    ]
    assert buckets[-1].reviewed == 1


async def test_global_history_honours_the_folder_window_rules(session):
    owner = await _user(session, "gh-window@example.com")
    today = datetime.now(UTC).date()

    with pytest.raises(ConflictError, match="history_window_invalid"):
        await global_history(
            _cu(owner), session, from_date=today, to_date=today - timedelta(days=1)
        )
    with pytest.raises(ConflictError, match="history_window_invalid"):
        await global_history(
            _cu(owner), session, from_date=today - timedelta(days=400), to_date=today
        )


async def test_global_history_with_no_tracked_senses_returns_empty_buckets(session):
    owner = await _user(session, "gh-empty@example.com")
    today = datetime.now(UTC).date()

    buckets = await global_history(
        _cu(owner), session, from_date=today - timedelta(days=1), to_date=today
    )

    assert len(buckets) == 2
    assert all(item.reviewed == 0 and item.avg_mastery == 0.0 for item in buckets)


# --- the mastered boundary --------------------------------------------------


async def test_mastered_uses_the_server_owned_80_floor(session):
    """The approved statistics threshold is 80, independent of visual bands."""
    from pycil.policy.policy import LEVEL_PROFILES, MASTERED_FLOOR

    assert MASTERED_FLOOR == 80
    assert LEVEL_PROFILES[-1].lo == 81

    owner = await _user(session, "gm-owner@example.com")
    await _stat(session, owner.id, 1, 79)
    await _stat(session, owner.id, 2, 80)

    stats_read = await global_stats(_cu(owner), session)

    assert stats_read.total == 2
    assert stats_read.learned == 2
    assert stats_read.mastered == 1


async def test_mastery_bands_tile_zero_to_one_hundred(session):
    from pycil.policy.policy import LEVEL_PROFILES, STAGE_NAMES, mastery_stage

    assert LEVEL_PROFILES[0].lo == 0
    assert LEVEL_PROFILES[-1].hi == 100
    for lower, upper in zip(LEVEL_PROFILES, LEVEL_PROFILES[1:], strict=False):
        assert upper.lo == lower.hi + 1, "the bands must tile with no gap or overlap"
    # Every mastery value maps to exactly one named stage.
    assert {mastery_stage(value) for value in range(0, 101)} == set(
        range(1, len(STAGE_NAMES) + 1)
    )


async def test_the_tracked_sense_read_is_bounded_and_truncates_deterministically(
    session, monkeypatch,
):
    """One pathological account cannot turn `/me/cefr` into an unbounded scan.

    The read used to pull every tracked sense id into memory. `/me/cefr` is its
    only caller — CEFR level is Lexi-side data a pycil query cannot group by — so
    the whole set crosses the process boundary on every request.

    The ceiling is far above any real learner's tracked set, so the real one is
    lowered here rather than seeding 20,001 rows: the assertion is that the LIMIT
    exists and that truncation is stable, and neither depends on the number.
    Deleting the `.limit()` makes this return every row and fail.

    Stability matters as much as the bound. The ORDER BY is what makes the
    truncated set the *same* set on every call, so a distribution built from it
    does not shuffle between requests — a bounded query without one would return
    whichever rows the plan happened to reach.
    """
    monkeypatch.setattr(reads, "TRACKED_SENSE_CEILING", 5)

    user = await _user(session, "bounded-cefr@example.com")
    # Inserted out of order, so passing cannot be an artefact of insertion order.
    for sense_id in (907, 901, 905, 903, 909, 902, 908, 904, 906):
        await _stat(session, user.id, sense_id, mastery=50)

    tracked = await reads.tracked_sense_ids(session, user.id)

    assert len(tracked) == 5, (
        f"the read returned {len(tracked)} ids with a ceiling of 5, so the LIMIT "
        "is not being applied"
    )
    # The numerically smallest, which is what the ORDER BY promises.
    assert tracked == [901, 902, 903, 904, 905]
    # And the same answer twice, since an unordered LIMIT may not repeat itself.
    assert await reads.tracked_sense_ids(session, user.id) == tracked
