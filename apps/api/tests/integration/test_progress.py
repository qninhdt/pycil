from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete

from pycil.account.models import User
from pycil.http import Problem
from pycil.library.models import DeckSense, Node, NodeRole, NodeSpace, NodeType
from pycil.library.tree import add_paths, roots
from pycil.study import progress as reports
from pycil.study.models import DailyActivity, UserSense

NOW = datetime(2026, 10, 2, 2, tzinfo=UTC)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


@pytest.fixture
async def tracked(database, user, senses, config, monkeypatch):
    monkeypatch.setattr(reports, "datetime", Clock)
    _, sessions, _ = database
    deck_ids = [uuid4(), uuid4()]
    other = User(clerk_subject="other_" + uuid4().hex, settings={})
    async with sessions() as session, session.begin():
        (await session.get(User, user.id)).settings = {"timezone": "America/New_York"}
        session.add(other)
        await session.flush()
        system = await roots(session, user.id)
        for identifier in deck_ids:
            node = Node(
                id=identifier,
                owner_id=user.id,
                type=NodeType.DECK,
                name="deck",
                parent_id=system[NodeRole.PERSONAL_ROOT].id,
                space=NodeSpace.PERSONAL,
            )
            session.add(node)
            await session.flush()
            await add_paths(session, node)
        session.add_all(DeckSense(deck_id=i, sense_id=1) for i in deck_ids)
        session.add(DeckSense(deck_id=deck_ids[0], sense_id=2))
        for sense_id, stability, due in ((1, 30, NOW), (2, 3, NOW + timedelta(days=1))):
            session.add(
                UserSense(
                    user_id=user.id,
                    sense_id=sense_id,
                    stability=stability,
                    difficulty=5,
                    last_exposure_at=NOW - timedelta(days=1),
                    due_at=due,
                    elo=600,
                    review_count=1,
                    lapse_count=0,
                )
            )
        day = NOW.date() - timedelta(days=1)
        session.add(DailyActivity(user_id=user.id, day=day, applied_events=2, practice_events=1))
        session.add(DailyActivity(user_id=other.id, day=day, applied_events=10, practice_events=0))
        # Lifetime longest is outside the activity window.
        for offset in range(5):
            session.add(
                DailyActivity(
                    user_id=user.id,
                    day=day - timedelta(days=500 + offset),
                    applied_events=1,
                    practice_events=0,
                )
            )
    return deck_ids, other


async def test_summary_partitions_and_independent_activity_schedule(
    database, user, config, tracked
):
    _, sessions, _ = database
    async with sessions() as session:
        summary = await reports.progress(session, user, config)
        activity = await reports.activity(session, user.id, config)
        schedule = await reports.schedule(session, user.id, config)
    assert (
        summary["total"],
        summary["studied"],
        summary["due"],
        summary["new"],
        summary["not_due"],
    ) == (2, 2, 1, 0, 1)
    assert summary["coverage"] == 1
    assert summary["reachable_decks"] == 2
    assert summary["last_studied_at"] == NOW - timedelta(days=1)
    assert activity["applied_events"] == 2 and activity["practice_events"] == 1
    assert activity["current_streak"] == 1 and activity["longest_streak"] == 5
    assert len(activity["days"]) == 366
    assert schedule["days"][0]["count"] == 0  # equality is DUE, not future work
    assert schedule["days"][1]["count"] == 1
    assert sum(day["count"] for day in schedule["days"]) == 1


async def test_membership_removal_changes_counts_not_activity(database, user, config, tracked):
    deck_ids, other = tracked
    _, sessions, _ = database
    async with sessions() as session, session.begin():
        await session.execute(delete(DeckSense).where(DeckSense.sense_id == 1))
    async with sessions() as session:
        summary = await reports.progress(session, user, config)
        scoped = await reports.progress(session, user, config, deck_ids[0])
        assert (summary["total"], summary["studied"], summary["due"]) == (1, 1, 0)
        assert scoped["total"] == 1
        assert (await reports.activity(session, user.id, config))["applied_events"] == 2
        assert await session.get(UserSense, (user.id, 1)) is not None
        with pytest.raises(Problem, match="node_not_found"):
            await reports.progress(session, other, config, deck_ids[0])


async def test_timezone_changes_do_not_regroup_daily_history(database, user, config, tracked):
    _, sessions, _ = database
    async with sessions() as session, session.begin():
        (await session.get(User, user.id)).settings = {"timezone": "Asia/Ho_Chi_Minh"}
    async with sessions() as session:
        activity = await reports.activity(session, user.id, config)
        assert activity["days"][-2]["applied_events"] == 2
        assert activity["current_streak"] == 1
        assert activity["longest_streak"] == 5
        with pytest.raises(Problem, match="invalid_date_window"):
            await reports.activity(session, user.id, config, NOW.date(), None)
