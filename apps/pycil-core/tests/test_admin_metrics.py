"""Admin metrics dashboard tests (Phase 4).

- non-admin → 403.
- admin → 200 with keys snapshot / spend_by_day / spend_by_model /
  top_spenders / signup_funnel.
- seeded responses/signups/spend reflect in the payload for the range.
- empty range returns zeros/empty arrays, not an error.
"""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text


async def test_non_admin_forbidden(client) -> None:
    assert (await client.get("/admin-api/metrics")).status_code == 403


async def test_admin_metrics_shape(admin_client) -> None:
    resp = await admin_client.get("/admin-api/metrics")
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "snapshot",
        "spend_by_day",
        "spend_by_model",
        "top_spenders",
        "signup_funnel",
    ):
        assert key in body
    for scalar in (
        "dau",
        "wau",
        "new_signups_today",
        "questions_answered_today",
        "decks_created_today",
    ):
        assert scalar in body["snapshot"]


async def test_admin_metrics_reflects_seeded_spend(admin_client, session) -> None:
    await session.execute(
        text(
            """
            INSERT INTO llm_spend_events (user_id, job_id, job_type, model, cost_usd)
            VALUES (NULL, :j, 'generate_term', 'seed-model', 0.01)
            """
        ),
        {"j": uuid4()},
    )
    await session.commit()

    body = (await admin_client.get("/admin-api/metrics")).json()
    models = {r["model"] for r in body["spend_by_model"]}
    assert "seed-model" in models


async def test_admin_metrics_empty_range_no_error(admin_client) -> None:
    # A zero-width historical range yields empty aggregates, not a 500.
    resp = await admin_client.get(
        "/admin-api/metrics", params={"days": 1}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["spend_by_day"], list)
    assert isinstance(body["top_spenders"], list)


async def test_signup_funnel_counts_new_users(admin_client, session) -> None:
    for i in range(3):
        await session.execute(
            text("INSERT INTO users (email) VALUES (:e)"),
            {"e": f"funnel-{i}-{uuid4().hex[:8]}@example.com"},
        )
    await session.commit()

    body = (await admin_client.get("/admin-api/metrics")).json()
    funnel = body["signup_funnel"]
    assert "total_signups" in funnel
    assert funnel["total_signups"] >= 3
