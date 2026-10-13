from datetime import UTC, datetime, timedelta

from pycil.app.config import load_config
from pycil.library.models import NodeRole, NodeType
from pycil.library.nodes import create_node, delete_node
from pycil.library.schemas import NodeCreate
from pycil.study import progress
from pycil.study.models import DailyActivity, UserSense
from tests.support.account import account
from tests.support.clock import frozen_datetime
from tests.support.vocabulary import neutral_word


async def test_overlapping_decks_and_references_count_distinct_senses_and_hide_anonymous_memory(
    database, monkeypatch
):
    config = load_config()
    owner, roots = await account(database.sessions)
    _, sense_id = await neutral_word(database.sessions)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(progress, "datetime", frozen_datetime(now))
    async with database.sessions() as session:
        deck = await create_node(
            session,
            owner.id,
            NodeCreate(type=NodeType.DECK, name="One", sense_ids=[sense_id]),
            config,
        )
    async with database.sessions() as session:
        await create_node(
            session,
            owner.id,
            NodeCreate(type=NodeType.DECK, name="Two", sense_ids=[sense_id]),
            config,
        )
    async with database.sessions() as session:
        await create_node(
            session,
            owner.id,
            NodeCreate(type=NodeType.REFERENCE, name="Alias", reference_id=deck["id"]),
            config,
        )
    async with database.sessions() as session, session.begin():
        session.add(
            UserSense(
                user_id=owner.id,
                sense_id=sense_id,
                stability=1,
                difficulty=5,
                elo=1000,
                last_exposure_at=now - timedelta(days=1),
                due_at=now,
                review_count=1,
                lapse_count=0,
            )
        )
    async with database.sessions() as session:
        values = await progress.summaries(
            session, owner.id, config, [roots[NodeRole.PERSONAL_ROOT].id, deck["id"]]
        )
    assert all(value["total"] == value["studied"] == value["due"] == 1 for value in values)
    assert all(value["new"] == value["not_due"] == 0 for value in values)
    async with database.sessions() as session:
        published = await create_node(
            session,
            owner.id,
            NodeCreate(
                type=NodeType.DECK,
                name="Public",
                parent_id=roots[NodeRole.PUBLISHED_ROOT].id,
                confirm_publication=True,
                sense_ids=[sense_id],
            ),
            config,
        )
    async with database.sessions() as session:
        anonymous = (await progress.summaries(session, None, config, [published["id"]]))[0]
    assert anonymous["total"] == 1
    assert anonymous["studied"] is anonymous["due"] is anonymous["coverage"] is None


async def test_schedule_excludes_overdue_and_equal_cutoff_and_uses_current_timezone(
    database, monkeypatch
):
    config = load_config()
    user, _ = await account(database.sessions, settings={"timezone": "Asia/Ho_Chi_Minh"})
    _, first = await neutral_word(database.sessions)
    # A second meaning of the same lexical word avoids duplicate identity fixtures.
    from pycil.vocabulary.enums import PartOfSpeech, Tier
    from pycil.vocabulary.models import Sense

    async with database.sessions() as session, session.begin():
        original = await session.get(Sense, first)
        second = Sense(word_id=original.word_id, pos=PartOfSpeech.NOUN, tier=Tier.CORE)
        session.add(second)
        await session.flush()
        second_id = second.id
    async with database.sessions() as session:
        deck = await create_node(
            session,
            user.id,
            NodeCreate(type=NodeType.DECK, name="Timing", sense_ids=[first, second_id]),
            config,
        )
    now = datetime(2026, 1, 1, 18, tzinfo=UTC)
    monkeypatch.setattr(progress, "datetime", frozen_datetime(now))
    async with database.sessions() as session, session.begin():
        for sense_id, due in [(first, now), (second_id, now + timedelta(hours=1))]:
            session.add(
                UserSense(
                    user_id=user.id,
                    sense_id=sense_id,
                    stability=1,
                    difficulty=5,
                    elo=1000,
                    last_exposure_at=now - timedelta(days=1),
                    due_at=due,
                    review_count=1,
                    lapse_count=0,
                )
            )
    async with database.sessions() as session:
        scheduled = await progress.schedule(session, user.id, config, deck["id"])
    assert scheduled["timezone"] == "Asia/Ho_Chi_Minh"
    assert scheduled["start_date"] == (now + timedelta(hours=7)).date()
    assert scheduled["days"][0]["count"] == 1
    assert sum(day["count"] for day in scheduled["days"]) == 1
    async with database.sessions() as session:
        await delete_node(session, user.id, deck["id"], config)
    async with database.sessions() as session:
        empty = await progress.schedule(session, user.id, config)
    assert sum(day["count"] for day in empty["days"]) == 0
    async with database.sessions() as session:
        assert await session.get(UserSense, (user.id, first)) is not None


async def test_activity_uses_stored_acceptance_dates_and_lifetime_streak_outside_window(
    database, monkeypatch
):
    config = load_config()
    user, _ = await account(database.sessions, settings={"timezone": "Asia/Ho_Chi_Minh"})
    now = datetime(2026, 1, 10, 18, tzinfo=UTC)
    monkeypatch.setattr(progress, "datetime", frozen_datetime(now))
    today = (now + timedelta(hours=7)).date()
    async with database.sessions() as session, session.begin():
        for offset in [0, 1, 4, 5, 6, 7]:
            session.add(
                DailyActivity(
                    user_id=user.id,
                    day=today - timedelta(days=offset),
                    applied_events=1,
                    practice_events=2,
                )
            )
    async with database.sessions() as session:
        report = await progress.activity(session, user.id, config, today - timedelta(days=2), today)
    assert report["current_streak"] == 2
    assert report["longest_streak"] == 4
    assert [day["applied_events"] for day in report["days"]] == [0, 1, 1]
    assert report["practice_events"] == 4
