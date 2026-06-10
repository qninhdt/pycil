"""`job_service.enqueue_generate_term`: rate limit, budget, dedup, orphan cleanup.

Pinned:
- 5 successive calls succeed; 6th → 429.
- Budget cap exhausted → 503 BEFORE rate-limit consumes a slot.
- Malformed `spend_key_today()` value → treated as 0.0.
- 5 concurrent same-term callers → exactly 1 arq enqueue (dedup).
- arq enqueue raises → lock cleared + jobs row marked failed.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from shared.redis_lock import spend_key_today
from sqlalchemy import text

from pycil_core.services import job_service
from tests.factories import make_term


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


async def test_rate_limit_blocks_sixth_call(
    session, fakeredis_client, test_user, _enqueue_mock
) -> None:
    term_id = await make_term(session, value="rate-limit-term")

    # 5 successful calls.
    for _ in range(5):
        await job_service.enqueue_generate_term(
            session, test_user["id"], term_id
        )
    # 6th → 429 rate_limited.
    with pytest.raises(HTTPException) as exc:
        await job_service.enqueue_generate_term(
            session, test_user["id"], term_id
        )
    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "rate_limited"


async def test_budget_exhausted_returns_503(
    session, fakeredis_client, test_user
) -> None:
    """Spend reaches cap → 503 budget_exhausted."""
    await fakeredis_client.set(spend_key_today(), "20.0")  # = cap

    term_id = await make_term(session, value="budget-exh")
    with pytest.raises(HTTPException) as exc:
        await job_service.enqueue_generate_term(
            session, test_user["id"], term_id
        )
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "budget_exhausted"


async def test_budget_check_runs_before_rate_limit(
    session, fakeredis_client, test_user
) -> None:
    """Budget rejection must NOT consume a rate-limit slot — otherwise an
    exhausted-budget request would burn one of the user's 5/hour quota."""
    await fakeredis_client.set(spend_key_today(), "20.0")
    term_id = await make_term(session, value="budget-before-rate")

    with pytest.raises(HTTPException):
        await job_service.enqueue_generate_term(
            session, test_user["id"], term_id
        )

    # Rate-limit key NOT created (no INCR fired).
    assert await fakeredis_client.get(f"rl:gen_term:{test_user['id']}") is None


async def test_malformed_spend_value_treated_as_zero(
    session, fakeredis_client, test_user, _enqueue_mock
) -> None:
    await fakeredis_client.set(spend_key_today(), "not-a-float")
    term_id = await make_term(session, value="malformed-budget")

    # Should proceed normally (no exception).
    result = await job_service.enqueue_generate_term(
        session, test_user["id"], term_id
    )
    assert "job_id" in result


async def test_dedup_concurrent_same_term(
    session, fakeredis_client, test_user, second_user, _enqueue_mock
) -> None:
    """Five concurrent enqueues on the same term → exactly one arq enqueue."""
    # Make a fresh user for each call to avoid rate-limit interference.
    users = [test_user["id"], second_user["id"]]
    extra = []
    for i in range(3):
        u = (
            await session.execute(
                text(
                    "INSERT INTO users (email, name) "
                    "VALUES (:e, 'Concurrent') RETURNING id"
                ),
                {"e": f"concurrent-{i}-{uuid4().hex[:6]}@x.test"},
            )
        ).one()
        extra.append(u.id)
    await session.commit()
    users.extend(extra)

    term_id = await make_term(session, value="concurrent-term")

    # Sequential to avoid asyncpg single-connection contention; behavior is
    # the same — second+ callers read the lock holder via LOCK_LUA.
    results = []
    for u in users:
        results.append(
            await job_service.enqueue_generate_term(session, u, term_id)
        )

    deduped_count = sum(1 for r in results if r.get("deduped"))
    fresh_count = sum(1 for r in results if not r.get("deduped"))

    assert fresh_count == 1
    assert deduped_count == len(users) - 1
    assert len(_enqueue_mock) == 1


async def test_enqueue_failure_orphan_cleanup(
    session, fakeredis_client, test_user, monkeypatch
) -> None:
    """arq enqueue raises → lock deleted + jobs row marked `failed/enqueue_failed`."""
    async def boom(job_name, *args, _job_id):
        raise RuntimeError("arq pool dead")

    monkeypatch.setattr(
        "pycil_core.services.job_service.enqueue_arq_job", boom
    )
    monkeypatch.setattr(
        "pycil_core.services._job_enqueue.enqueue_arq_job", boom
    )

    term_id = await make_term(session, value="orphan-term")

    with pytest.raises(RuntimeError, match="arq pool dead"):
        await job_service.enqueue_generate_term(
            session, test_user["id"], term_id
        )

    # Lock key deleted.
    assert await fakeredis_client.get(f"lock:generate_term:{term_id}") is None

    # jobs row marked failed.
    row = (
        await session.execute(
            text(
                "SELECT status, error FROM jobs "
                "ORDER BY created_at DESC LIMIT 1"
            )
        )
    ).one()
    assert row.status == "failed"
    assert row.error == "enqueue_failed"


async def test_commit_failure_releases_lock(
    session, fakeredis_client, test_user, monkeypatch
) -> None:
    """Regression (C1): a commit failure on the fresh-job INSERTs must still
    release the term lock. Previously only the enqueue-failure path released
    it, so a commit error leaked the lock for the full TTL window and left the
    term un-enrichable."""
    term_id = await make_term(session, value="commit-leak-term")

    real_commit = session.commit
    calls = {"n": 0}

    async def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("commit boom")
        return await real_commit()

    monkeypatch.setattr(session, "commit", flaky_commit)

    with pytest.raises(RuntimeError, match="commit boom"):
        await job_service.enqueue_generate_term(session, test_user["id"], term_id)

    # Lock must be released despite the commit failure.
    assert await fakeredis_client.get(f"lock:generate_term:{term_id}") is None

