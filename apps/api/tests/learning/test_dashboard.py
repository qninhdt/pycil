"""Dashboard stats endpoint integration test."""

from datetime import UTC, datetime, timedelta

import pytest

from pycil.auth.models import User
from pycil.auth.tokens import sign_access
from pycil.learning.models import UserSenseStats

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
