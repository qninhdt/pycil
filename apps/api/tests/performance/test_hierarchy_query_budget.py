"""Opt-in measured query budget for the array-bound hierarchy stats path."""

import os
from time import perf_counter

import pytest
from sqlalchemy import text

from pycil.auth.models import User
from pycil.hierarchy import stats

pytestmark = pytest.mark.performance


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("RUN_HIERARCHY_PERFORMANCE") != "1",
    reason="set RUN_HIERARCHY_PERFORMANCE=1 to load 100k synthetic stats rows",
)
async def test_array_bound_folder_stats_budget(session):
    """Record 2k/100k timings without creating permanent analytics tables."""
    user = User(email="performance@example.com")
    session.add(user)
    await session.commit()
    sense_ids = list(range(1, 100_001))
    await session.execute(
        text(
            """
            INSERT INTO user_sense_stats (
                user_id, sense_id, stability, difficulty, mastery, interval_days,
                review_count, lapse_count, status
            )
            SELECT CAST(:user_id AS uuid), sense_id, 10, 5, 75, 1, 1, 0, 'review'
            FROM unnest(CAST(:sense_ids AS bigint[])) AS sense_id
            """
        ),
        {"user_id": str(user.id), "sense_ids": sense_ids},
    )
    await session.commit()

    started = perf_counter()
    two_thousand = await stats.folder_stats(session, user.id, sense_ids[:2_000])
    elapsed_2k_ms = (perf_counter() - started) * 1_000

    started = perf_counter()
    one_hundred_thousand = await stats.folder_stats(session, user.id, sense_ids)
    elapsed_100k_ms = (perf_counter() - started) * 1_000

    assert two_thousand.learned == 2_000
    assert one_hundred_thousand.learned == 100_000
    # This is intentionally a local measurement gate, not a CI hardware claim.
    assert elapsed_2k_ms < 50
    print(f"hierarchy_stats_2k_ms={elapsed_2k_ms:.2f}")
    print(f"hierarchy_stats_100k_ms={elapsed_100k_ms:.2f}")
