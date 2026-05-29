"""Term batch ingestion service (P2 phase 1).

Wraps `term_service.add_term_to_deck` for bulk paste / CSV / Anki / extension
flows. Per-batch budget pre-flight + per-user batch rate limit enforced
before any LLM job is enqueued.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from shared.db import Definition, Term
from sqlalchemy import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from pycil_core.services.job_service import enqueue_generate_term
from pycil_core.services.term_service import add_term_to_deck

TermSource = Literal[
    "manual", "bulk_paste", "csv", "anki", "quizlet", "extension", "ocr", "pdf", "epub"
]

MAX_BATCH_SIZE = 200
DAILY_BATCH_TERM_CAP = 500
ESTIMATED_COST_PER_TERM_USD = 0.0005
GLOBAL_SPEND_KEY_PREFIX = "openrouter:spend:daily"


@dataclass
class BatchOutcome:
    value: str
    status: Literal["created", "existing", "invalid", "rejected"]
    job_id: str | None = None
    error: str | None = None


@dataclass
class BatchResult:
    accepted: int
    deduped: int
    rejected: int
    job_ids: list[str]
    outcomes: list[BatchOutcome]


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())[:200]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        n = _normalize(raw)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


async def _check_batch_rate_limit(redis: Redis, user_id: UUID, n: int) -> None:
    """1 batch/min and DAILY_BATCH_TERM_CAP terms/day per user."""
    today = date.today().isoformat()
    minute_key = f"rl:gen_term_batch:min:{user_id}"
    daily_key = f"rl:gen_term_batch:day:{user_id}:{today}"

    minute = await redis.incr(minute_key)
    if minute == 1:
        await redis.expire(minute_key, 60)
    if minute > 1:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "batch_rate_limit_per_minute"
        )

    daily = await redis.incrby(daily_key, n)
    if daily == n:
        await redis.expire(daily_key, 60 * 60 * 25)
    if daily > DAILY_BATCH_TERM_CAP:
        await redis.incrby(daily_key, -n)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "batch_daily_term_cap"
        )


async def _check_batch_budget(
    redis: Redis, n_new: int, daily_cap_usd: float
) -> None:
    """Reject if projected batch spend exceeds 50% of remaining cap."""
    today = date.today().isoformat()
    spent = await redis.get(f"{GLOBAL_SPEND_KEY_PREFIX}:{today}")
    spent_f = float(spent) if spent else 0.0
    projected = n_new * ESTIMATED_COST_PER_TERM_USD
    safety_margin = 0.5
    if spent_f + projected > daily_cap_usd * (1.0 - safety_margin):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "batch_over_global_budget"
        )


async def _term_already_enriched(session: AsyncSession, term_id: int) -> bool:
    """Skip enqueue when canonical enrichment is already cached."""
    row = (
        await session.exec(
            select(Definition.id).where(Definition.term_id == term_id).limit(1)
        )
    ).first()
    return row is not None


async def add_terms_batch(
    session: AsyncSession,
    redis: Redis,
    user_id: UUID,
    deck_id: UUID,
    raw_values: list[str],
    *,
    source: TermSource = "bulk_paste",
    daily_cap_usd: float = 20.0,
) -> BatchResult:
    if len(raw_values) > MAX_BATCH_SIZE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "batch_too_large"
        )
    deduped = _dedupe(raw_values)
    if not deduped:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "batch_empty")

    await _check_batch_rate_limit(redis, user_id, len(deduped))
    await _check_batch_budget(redis, len(deduped), daily_cap_usd)

    outcomes: list[BatchOutcome] = []
    job_ids: list[str] = []
    for value in deduped:
        try:
            resp = await add_term_to_deck(session, user_id, deck_id, value)
            term_id = resp.term.id
            if await _term_already_enriched(session, term_id):
                outcomes.append(BatchOutcome(value=value, status="existing"))
                continue
            enqueued = await enqueue_generate_term(
                session, user_id, term_id, skip_user_rate=True
            )
            job_id = enqueued["job_id"]
            outcomes.append(
                BatchOutcome(value=value, status="created", job_id=job_id)
            )
            job_ids.append(job_id)
        except HTTPException as exc:
            outcomes.append(
                BatchOutcome(value=value, status="invalid", error=str(exc.detail))
            )

    if outcomes:
        await session.exec(
            update(Term)
            .where(
                Term.value.in_(
                    [o.value for o in outcomes if o.status != "invalid"]
                ),
                Term.source == "manual",
            )
            .values(source=source)
        )
        await session.commit()

    accepted = sum(1 for o in outcomes if o.status == "created")
    deduped_n = sum(1 for o in outcomes if o.status == "existing")
    rejected = sum(1 for o in outcomes if o.status in ("invalid", "rejected"))
    return BatchResult(
        accepted=accepted,
        deduped=deduped_n,
        rejected=rejected,
        job_ids=job_ids,
        outcomes=outcomes,
    )
