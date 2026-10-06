from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, text

from pycil.account.models import User
from pycil.http import Problem
from pycil.library.models import DeckSense, Node, NodeRole, NodeSpace, NodeType
from pycil.library.tree import add_paths, roots
from pycil.study import progress as reports
from pycil.study.fsrs import mastery
from pycil.study.models import Rating, ReviewLog, SenseMemory

NOW = datetime(2026, 10, 2, 2, tzinfo=UTC)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


@pytest.fixture
async def activity(database, user, senses, config, monkeypatch):
    monkeypatch.setattr(reports, "datetime", Clock)
    _, sessions, _ = database
    user.settings = {"timezone": "America/New_York"}
    deck_ids = [uuid4(), uuid4()]
    other = User(clerk_subject="user_other_" + uuid4().hex, settings={})
    async with sessions() as session, session.begin():
        session.add(other)
        await session.flush()
        system = await roots(session, user.id)
        for deck_id in deck_ids:
            node = Node(
                id=deck_id,
                owner_id=user.id,
                type=NodeType.DECK,
                name="deck",
                parent_id=system[NodeRole.PERSONAL_ROOT].id,
                space=NodeSpace.PERSONAL,
            )
            session.add(node)
            await session.flush()
            await add_paths(session, node)
        await session.flush()
        session.add_all(DeckSense(deck_id=i, sense_id=1) for i in deck_ids)
        session.add(DeckSense(deck_id=deck_ids[0], sense_id=2))
        for sense_id, stability, due in ((1, 30, NOW), (2, 3, NOW + timedelta(days=1))):
            session.add(
                SenseMemory(
                    user_id=user.id,
                    sense_id=sense_id,
                    stability=stability,
                    difficulty=5,
                    last_review_at=NOW - timedelta(days=1),
                    due_at=due,
                    last_rating=Rating.GOOD,
                    review_count=1,
                    lapse_count=0,
                )
            )
        for owner, sense_id, when, applied in (
            (user.id, 1, NOW - timedelta(hours=3), True),
            (user.id, 1, NOW - timedelta(hours=1), False),
            (user.id, 2, NOW - timedelta(hours=1), True),
            (other.id, 1, NOW - timedelta(hours=1), True),
            (user.id, 1, NOW - timedelta(days=config.learning.limits.max_history_days + 1), True),
        ):
            session.add(
                ReviewLog(
                    user_id=owner,
                    event_key=uuid4(),
                    sense_id=sense_id,
                    rating=Rating.GOOD,
                    accepted_at=when,
                    applied=applied,
                    mastery_after=50,
                    due_after=NOW,
                )
            )
        await session.execute(text("UPDATE lexi.senses SET cefr_level='B1' WHERE id=1"))
    return deck_ids, other


async def test_progress_deduplicates_scope_and_counts_local_activity(
    database, user, config, activity
):
    _, sessions, _ = database
    async with sessions() as session:
        result = await reports.progress(session, user, config)
    assert result["summary"] == {"total": 2, "learned": 2, "due": 1}
    assert result["activity"] == [
        {
            "day": "2026-10-01",
            "applied_reviews": 2,
            "practice_events": 1,
        }
    ]
    assert result["forecast"] == [
        {"day": "2026-10-01", "count": 1},
        {"day": "2026-10-02", "count": 1},
    ]
    assert result["weakest_senses"] == [
        {"sense_id": 2, "mastery": mastery(3, config)},
        {"sense_id": 1, "mastery": 50},
    ]
    assert {r["cefr_level"]: r["count"] for r in result["cefr_distribution"]} == {"B1": 1, None: 1}


async def test_global_memory_survives_membership_removal_but_scoped_counts_do_not(
    database,
    user,
    config,
    activity,
):
    deck_ids, other = activity
    _, sessions, _ = database
    async with sessions() as session, session.begin():
        await session.execute(delete(DeckSense).where(DeckSense.sense_id == 1))
    async with sessions() as session:
        global_result = await reports.progress(session, user, config)
        scoped = await reports.progress(session, user, config, deck_ids[0])
        assert global_result["summary"] == {"total": 1, "learned": 1, "due": 0}
        assert scoped["summary"] == {"total": 1, "learned": 1, "due": 0}
        assert scoped["activity"][0]["applied_reviews"] == 1
        assert scoped["activity"][0]["practice_events"] == 0
        with pytest.raises(Problem, match="node_not_found"):
            await reports.progress(session, other, config, deck_ids[0])


async def test_history_tied_timestamp_pagination_is_user_isolated(database, user, config, activity):
    _, other = activity
    _, sessions, _ = database
    config = config.model_copy(
        update={
            "learning": config.learning.model_copy(
                update={
                    "limits": config.learning.limits.model_copy(update={"history_page_size": 1}),
                }
            )
        }
    )
    async with sessions() as session:
        seen, cursor = [], None
        for _ in range(4):
            page = await reports.history(session, user, config, days=2, after=cursor)
            seen += page["events"]
            cursor = page["next_after"]
            if cursor is None:
                break
        assert len(seen) == len({e["event_key"] for e in seen}) == 3
        assert all(e["user_id"] == user.id for e in seen)
        assert sum(e["applied"] for e in seen) == 2
        assert (await reports.history(session, other, config, days=2))["applied_count"] == 1
        with pytest.raises(Problem, match="invalid_cursor"):
            await reports.history(session, other, config, after=seen[0]["event_key"])
        with pytest.raises(Problem, match="invalid_history_window"):
            await reports.history(session, user, config, days=0)
