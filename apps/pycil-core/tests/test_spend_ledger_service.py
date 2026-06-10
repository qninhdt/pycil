"""spend_ledger_service aggregation tests (Phase 3, core side).

Seeds llm_spend_events rows and asserts spend_by_day / spend_by_model /
top_spenders return correct aggregates over a date range.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from pycil_core.services import spend_ledger_service


async def _seed_event(
    session,
    *,
    user_id: str | None,
    model: str,
    cost: float,
    job_type: str = "generate_question",
    created_at: datetime | None = None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO llm_spend_events
              (user_id, job_id, job_type, model, cost_usd, created_at)
            VALUES
              (CAST(:uid AS uuid), :jid, :jt, :model, :cost,
               COALESCE(:ts, NOW()))
            """
        ),
        {
            "uid": user_id,
            "jid": uuid4(),
            "jt": job_type,
            "model": model,
            "cost": cost,
            "ts": created_at,
        },
    )
    await session.commit()


async def test_spend_by_model_aggregates(session) -> None:
    await _seed_event(session, user_id=None, model="model-a", cost=0.001)
    await _seed_event(session, user_id=None, model="model-a", cost=0.002)
    await _seed_event(session, user_id=None, model="model-b", cost=0.005)

    start = datetime.now(UTC) - timedelta(days=1)
    end = datetime.now(UTC) + timedelta(days=1)
    rows = await spend_ledger_service.spend_by_model(session, start=start, end=end)

    by_model = {r["model"]: r for r in rows}
    assert by_model["model-a"]["calls"] == 2
    assert by_model["model-a"]["cost_usd"] == round(0.003, 6)
    assert by_model["model-b"]["cost_usd"] == round(0.005, 6)
    # Ordered by descending spend.
    assert rows[0]["model"] == "model-b"


async def test_spend_by_day_aggregates(session) -> None:
    today = datetime.now(UTC)
    yesterday = today - timedelta(days=1)
    await _seed_event(session, user_id=None, model="m", cost=0.001, created_at=yesterday)
    await _seed_event(session, user_id=None, model="m", cost=0.002, created_at=today)
    await _seed_event(session, user_id=None, model="m", cost=0.003, created_at=today)

    start = today - timedelta(days=3)
    end = today + timedelta(days=1)
    rows = await spend_ledger_service.spend_by_day(session, start=start, end=end)
    assert len(rows) == 2
    # Most recent day has 2 calls summing to 0.005.
    latest = rows[-1]
    assert latest["calls"] == 2
    assert latest["cost_usd"] == round(0.005, 6)


async def test_top_spenders_excludes_null_user(session) -> None:
    u1 = (
        await session.execute(
            text("INSERT INTO users (email) VALUES (:e) RETURNING id"),
            {"e": f"u1-{uuid4().hex[:8]}@example.com"},
        )
    ).one().id
    u2 = (
        await session.execute(
            text("INSERT INTO users (email) VALUES (:e) RETURNING id"),
            {"e": f"u2-{uuid4().hex[:8]}@example.com"},
        )
    ).one().id
    await session.commit()

    await _seed_event(session, user_id=str(u1), model="m", cost=0.010)
    await _seed_event(session, user_id=str(u2), model="m", cost=0.030)
    # NULL-user (generate_term global cache) row must NOT appear.
    await _seed_event(session, user_id=None, model="m", cost=99.0, job_type="generate_term")

    start = datetime.now(UTC) - timedelta(days=1)
    end = datetime.now(UTC) + timedelta(days=1)
    rows = await spend_ledger_service.top_spenders(
        session, start=start, end=end, limit=10
    )

    ids = {r["user_id"] for r in rows}
    assert str(u1) in ids and str(u2) in ids
    # No NULL/global-cache rows.
    assert all(r["user_id"] is not None for r in rows)
    # Ordered: u2 (0.03) before u1 (0.01).
    assert rows[0]["user_id"] == str(u2)


async def test_range_excludes_out_of_window(session) -> None:
    old = datetime.now(UTC) - timedelta(days=10)
    await _seed_event(session, user_id=None, model="m", cost=5.0, created_at=old)

    start = datetime.now(UTC) - timedelta(days=1)
    end = datetime.now(UTC) + timedelta(days=1)
    rows = await spend_ledger_service.spend_by_model(session, start=start, end=end)
    assert rows == []
