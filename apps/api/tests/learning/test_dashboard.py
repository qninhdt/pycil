"""Dashboard stats endpoint integration test."""

from datetime import UTC, datetime, timedelta

import pytest

from pycil.auth.models import User
from pycil.auth.tokens import sign_access
from pycil.learning.infra.models import UserSenseStats

pytestmark = pytest.mark.asyncio


async def test_get_dashboard_stats(client, session):
    user = User(email="dashlearner@test.co")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    now = datetime.now(UTC)
    s1 = UserSenseStats(
        user_id=user.id,
        sense_id=101,
        mastery=75,
        review_count=3,
        next_review_date=now - timedelta(hours=1),
    )
    s2 = UserSenseStats(
        user_id=user.id,
        sense_id=102,
        mastery=90,
        review_count=5,
        next_review_date=now + timedelta(days=2),
    )
    session.add_all([s1, s2])
    await session.commit()

    token, _ = sign_access(user)
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.get("/v1/learning/dashboard", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["totalLearnedWords"] == 2
    assert data["dueTodayCount"] == 1
    assert data["masteryPercentage"] == 82.5
    assert len(data["fsrsForecast"]) == 7


async def test_recent_session_points_at_the_deck_actually_reviewed(client, session):
    """B5. `recentSession` is the dashboard's "continue where you left off".

    It reads the newest `ReviewLog` carrying a `node_id` (`router.py:198`). The
    column existed but nothing populated it, so the query matched nothing and the
    endpoint silently fell back to "the caller's first deck, whichever that is" —
    which is wrong the moment a learner owns more than one deck, and was wrong for
    every row in the database (measured: 160 of 160 NULL).

    Two decks here, and the review is recorded in the SECOND one, so the fallback
    and the correct answer are different values and the assertion can tell them
    apart.
    """
    from pycil.hierarchy.application import service as hierarchy_service
    from pycil.hierarchy.infra.models import NodeType
    from pycil.learning.infra.models import ReviewLog

    user = User(email="recent-session@test.co")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    first = await hierarchy_service.create_node(
        session, user.id, node_type=NodeType.DECK, name="the fallback deck"
    )
    reviewed = await hierarchy_service.create_node(
        session, user.id, node_type=NodeType.DECK, name="the deck actually studied"
    )

    session.add(
        ReviewLog(
            user_id=user.id,
            sense_id=404,
            node_id=reviewed.id,
            stability_before=1.0,
            stability_after=2.0,
            mastery_before=10,
            mastery_after=20,
            grade=3,
        )
    )
    await session.commit()

    token, _ = sign_access(user)
    res = await client.get(
        "/v1/learning/dashboard", headers={"Authorization": f"Bearer {token}"}
    )

    assert res.status_code == 200
    recent = res.json()["recentSession"]
    assert recent is not None, "a review with a node_id must produce a recentSession"
    assert recent["nodeId"] == str(reviewed.id), (
        "recentSession must name the deck that was reviewed, not the first deck "
        f"({first.name!r}) the fallback would pick"
    )
    assert recent["deckTitle"] == "the deck actually studied"
