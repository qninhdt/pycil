"""`term_batch_service.add_terms_batch`: enqueue, dedup, rate, budget, cap.

Pinned:
- 50 fresh terms → 50 jobs enqueued, source stamped.
- All-duplicate payload collapses; existing-enriched terms skip enqueue.
- Mixed 50/50 (some pre-enriched, some new) routes correctly.
- 201-value payload → 422 batch_too_large BEFORE any enqueue.
- Spend within remaining-half-of-cap → 503 batch_over_global_budget.
- Same-user second batch within 60s → 429 batch_rate_limit_per_minute.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from pycil_core.services import term_batch_service
from tests.factories import make_deck, make_definition, make_term


@pytest.fixture(autouse=True)
def _budget_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_BUDGET_DAILY_USD", "20")


@pytest.fixture
def _enqueue_mock(monkeypatch):
    calls: list[dict] = []

    async def fake(job_name, *args, _job_id):
        calls.append({"name": job_name, "args": args, "job_id": _job_id})

    monkeypatch.setattr(
        "pycil_core.services.job_service.enqueue_arq_job", fake
    )
    monkeypatch.setattr(
        "pycil_core.services._job_enqueue.enqueue_arq_job", fake
    )
    return calls


async def test_happy_50_terms_enqueues_each(
    session, fakeredis_client, test_user, _enqueue_mock
) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    values = [f"term-{i}" for i in range(50)]

    result = await term_batch_service.add_terms_batch(
        session,
        fakeredis_client,
        test_user["id"],
        deck["id"],
        values,
        source="bulk_paste",
    )

    assert result.accepted == 50
    assert result.deduped == 0
    assert result.rejected == 0
    assert len(result.job_ids) == 50
    assert len(_enqueue_mock) == 50
    # Source stamped on the new term rows.
    rows = (
        await session.execute(
            text("SELECT source FROM terms WHERE value = ANY(:vals)"),
            {"vals": values},
        )
    ).all()
    assert all(r.source == "bulk_paste" for r in rows)


async def test_all_duplicates_collapse_to_one(
    session, fakeredis_client, test_user, _enqueue_mock
) -> None:
    """Same term repeated 200 times → deduped to 1 enqueue."""
    deck = await make_deck(session, author_id=test_user["id"])
    values = ["recurring"] * 200

    result = await term_batch_service.add_terms_batch(
        session, fakeredis_client, test_user["id"], deck["id"], values
    )

    assert result.accepted == 1
    assert result.deduped == 0  # no pre-existing enrichment, so it's "created"
    assert len(_enqueue_mock) == 1


async def test_mixed_pre_enriched_and_new(
    session, fakeredis_client, test_user, _enqueue_mock
) -> None:
    """Pre-enriched terms skip enqueue; fresh terms enqueue."""
    deck = await make_deck(session, author_id=test_user["id"])

    # Seed 5 already-enriched terms (have a definition row).
    cached_values = [f"cached-{i}" for i in range(5)]
    for v in cached_values:
        tid = await make_term(session, value=v)
        await make_definition(session, term_id=tid)

    fresh_values = [f"fresh-{i}" for i in range(5)]
    payload = cached_values + fresh_values

    result = await term_batch_service.add_terms_batch(
        session, fakeredis_client, test_user["id"], deck["id"], payload
    )

    assert result.accepted == 5
    assert result.deduped == 5
    assert len(_enqueue_mock) == 5  # only fresh ones enqueued


async def test_over_max_batch_size_rejects_422(
    session, fakeredis_client, test_user, _enqueue_mock
) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    values = [f"x{i}" for i in range(term_batch_service.MAX_BATCH_SIZE + 1)]

    with pytest.raises(HTTPException) as exc:
        await term_batch_service.add_terms_batch(
            session, fakeredis_client, test_user["id"], deck["id"], values
        )
    assert exc.value.status_code == 422
    assert exc.value.detail == "batch_too_large"
    assert len(_enqueue_mock) == 0


async def test_over_batch_budget_rejects_503(
    session, fakeredis_client, test_user, _enqueue_mock
) -> None:
    """Spent so close to cap that projected batch crosses 50% safety margin."""
    from datetime import date

    today = date.today().isoformat()
    # daily_cap=20.0, safety_margin=0.5 → reject if spent + projected > 10.0.
    # Pre-spend $9.99 leaves $0.01 of headroom, smaller than even 1 term * 0.0005.
    # Wait — that's $0.005 projected, still under $0.01 so it would pass.
    # Push spent above the half-cap so any non-zero projection crosses.
    await fakeredis_client.set(
        f"{term_batch_service.GLOBAL_SPEND_KEY_PREFIX}:{today}", "10.0"
    )
    deck = await make_deck(session, author_id=test_user["id"])
    values = ["alpha", "beta", "gamma"]

    with pytest.raises(HTTPException) as exc:
        await term_batch_service.add_terms_batch(
            session, fakeredis_client, test_user["id"], deck["id"], values
        )
    assert exc.value.status_code == 503
    assert exc.value.detail == "batch_over_global_budget"
    assert len(_enqueue_mock) == 0


async def test_second_batch_within_minute_rate_limited(
    session, fakeredis_client, test_user, _enqueue_mock
) -> None:
    """1 batch/min — second call within the window → 429."""
    deck = await make_deck(session, author_id=test_user["id"])

    # First batch succeeds.
    await term_batch_service.add_terms_batch(
        session, fakeredis_client, test_user["id"], deck["id"], ["alpha"]
    )

    # Second batch (different terms) → 429.
    with pytest.raises(HTTPException) as exc:
        await term_batch_service.add_terms_batch(
            session, fakeredis_client, test_user["id"], deck["id"], ["beta"]
        )
    assert exc.value.status_code == 429
    assert exc.value.detail == "batch_rate_limit_per_minute"
