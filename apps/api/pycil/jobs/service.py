"""Persistence operations for durable word-generation jobs."""

import unicodedata
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.retry import next_attempt_delay
from pycil.jobs.models import JobStatus, WordGeneration

LEASE_SECONDS = 120

_RESERVE_QUOTA = """
local limits = {tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3]), tonumber(ARGV[4])}
for i = 1, 4 do
  if tonumber(redis.call('GET', KEYS[i]) or '0') >= limits[i] then return 0 end
end
for i = 1, 4 do
  redis.call('INCR', KEYS[i])
  if i <= 2 then redis.call('EXPIRE', KEYS[i], tonumber(ARGV[4 + i])) end
  if i >= 3 then redis.call('EXPIRE', KEYS[i], tonumber(ARGV[7])) end
end
return 1
"""

_RELEASE_INFLIGHT = """
for i = 1, 2 do
  local value = tonumber(redis.call('GET', KEYS[i]) or '0')
  if value <= 1 then redis.call('DEL', KEYS[i]) else redis.call('DECR', KEYS[i]) end
end
return 1
"""


def _now() -> datetime:
    return datetime.now(UTC)


def _quota_keys(owner_id: UUID, now: datetime) -> tuple[str, str, str, str]:
    return (
        f"word-generation:hour:{owner_id}:{now.strftime('%Y%m%d%H')}",
        f"word-generation:day:{now.strftime('%Y%m%d')}",
        f"word-generation:inflight:user:{owner_id}",
        "word-generation:inflight:global",
    )


async def reserve_quota(redis: Redis, owner_id: UUID) -> bool:
    """Atomically charge a request and reserve its two durable inflight slots."""
    from pycil.config import settings

    now = _now()
    seconds_to_midnight = (
        int((now.replace(hour=23, minute=59, second=59, microsecond=0) - now).total_seconds()) + 1
    )
    return bool(
        await redis.eval(
            _RESERVE_QUOTA,
            4,
            *_quota_keys(owner_id, now),
            settings.word_generation_requests_per_hour,
            settings.word_generation_daily_limit,
            settings.word_generation_max_inflight_per_user,
            settings.word_generation_max_inflight_global,
            3600,
            seconds_to_midnight,
            # A worker lease lasts two minutes and retry backoff tops out at
            # two minutes; this bound prevents permanent quota leakage if a
            # process disappears before its terminal cleanup.
            900,
        )
    )


async def release_inflight_quota(redis: Redis, owner_id: UUID) -> None:
    await redis.eval(_RELEASE_INFLIGHT, 2, *_quota_keys(owner_id, _now())[2:])


def normalize_query(query: str) -> str:
    """Produce a stable lookup key without changing the submitted query."""
    return " ".join(unicodedata.normalize("NFKC", query).casefold().split())


async def create_generation(session: AsyncSession, owner_id: UUID, query: str) -> WordGeneration:
    record = WordGeneration(
        owner_id=owner_id,
        query=query,
        normalized_query=normalize_query(query),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def create_or_retrieve_generation(
    session: AsyncSession,
    owner_id: UUID,
    query: str,
    idempotency_key: str | None,
) -> tuple[WordGeneration, bool]:
    """Create one submission per owner/key, safely converging racing requests."""
    if not idempotency_key:
        return await create_generation(session, owner_id, query), True

    statement = select(WordGeneration).where(
        WordGeneration.owner_id == owner_id,
        WordGeneration.idempotency_key == idempotency_key,
    )
    existing = (await session.execute(statement)).scalar_one_or_none()
    if existing is not None:
        return existing, False

    record = WordGeneration(
        owner_id=owner_id,
        query=query,
        normalized_query=normalize_query(query),
        idempotency_key=idempotency_key,
    )
    session.add(record)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = (await session.execute(statement)).scalar_one()
        return existing, False
    await session.refresh(record)
    return record, True


async def submit_generation(
    session: AsyncSession,
    redis: Redis,
    owner_id: UUID,
    query: str,
    idempotency_key: str | None,
) -> tuple[WordGeneration, bool, bool]:
    """Return record/created/quota_allowed; replay is inspected before charging."""
    if idempotency_key:
        existing = await session.scalar(
            select(WordGeneration).where(
                WordGeneration.owner_id == owner_id,
                WordGeneration.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing, False, True
    if not await reserve_quota(redis, owner_id):
        return (
            WordGeneration(owner_id=owner_id, query=query, normalized_query=normalize_query(query)),
            False,
            False,
        )
    try:
        record, created = await create_or_retrieve_generation(
            session, owner_id, query, idempotency_key
        )
    except Exception:
        await release_inflight_quota(redis, owner_id)
        raise
    if not created:
        # A concurrent idempotent insert won after our preflight lookup.
        await release_inflight_quota(redis, owner_id)
    return record, created, True


async def get_generation(
    session: AsyncSession, job_id: UUID, owner_id: UUID
) -> WordGeneration | None:
    statement = select(WordGeneration).where(
        WordGeneration.id == job_id,
        WordGeneration.owner_id == owner_id,
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def list_claimable_generations(
    session: AsyncSession, limit: int = 100
) -> list[WordGeneration]:
    now = _now()
    statement = (
        select(WordGeneration)
        .where(
            or_(
                (WordGeneration.status == JobStatus.QUEUED)
                & (WordGeneration.next_attempt_at <= now),
                (WordGeneration.status == JobStatus.RUNNING)
                & (WordGeneration.lease_expires_at <= now),
            )
        )
        .order_by(WordGeneration.next_attempt_at, WordGeneration.id)
        .limit(limit)
    )
    return list((await session.execute(statement)).scalars())


async def claim_generation(
    session: AsyncSession,
    job_id: UUID,
    lease_owner: str,
    *,
    lease_seconds: int = LEASE_SECONDS,
    redis: Redis | None = None,
) -> WordGeneration | None:
    """Acquire a fenced lease only for due work or an expired worker lease."""
    now = _now()
    record = await session.scalar(
        select(WordGeneration).where(WordGeneration.id == job_id).with_for_update()
    )
    if record is None:
        return None
    eligible = (
        record.status == JobStatus.QUEUED
        and record.next_attempt_at is not None
        and record.next_attempt_at <= now
    ) or (
        record.status == JobStatus.RUNNING
        and record.lease_expires_at is not None
        and record.lease_expires_at <= now
    )
    if not eligible:
        return None
    if record.attempt >= record.max_attempts:
        record.status = JobStatus.FAILED
        record.error_code = "lease_expired"
        record.lease_owner = record.lease_token = None
        record.lease_expires_at = None
        await session.commit()
        await session.refresh(record)
        if redis is not None:
            await release_inflight_quota(redis, record.owner_id)
        return None
    record.status = JobStatus.RUNNING
    record.attempt += 1
    record.lease_owner = lease_owner
    record.lease_token = str(uuid4())
    record.lease_fence += 1
    record.lease_expires_at = now + timedelta(seconds=lease_seconds)
    await session.commit()
    await session.refresh(record)
    return record


async def complete_generation(
    session: AsyncSession, job_id: UUID, lease_token: str, lease_fence: int, result: dict
) -> WordGeneration | None:
    record = await session.scalar(
        select(WordGeneration).where(WordGeneration.id == job_id).with_for_update()
    )
    if (
        record is None
        or record.status != JobStatus.RUNNING
        or record.lease_token != lease_token
        or record.lease_fence != lease_fence
    ):
        return None
    record.status = JobStatus.SUCCEEDED
    record.result = result
    record.error_code = None
    record.lease_owner = record.lease_token = None
    record.lease_expires_at = None
    await session.commit()
    await session.refresh(record)
    return record


async def fail_generation(
    session: AsyncSession, job_id: UUID, lease_token: str, lease_fence: int, error_code: str
) -> WordGeneration | None:
    record = await session.scalar(
        select(WordGeneration).where(WordGeneration.id == job_id).with_for_update()
    )
    if (
        record is None
        or record.status != JobStatus.RUNNING
        or record.lease_token != lease_token
        or record.lease_fence != lease_fence
    ):
        return None
    terminal = record.attempt >= record.max_attempts
    record.status = JobStatus.FAILED if terminal else JobStatus.QUEUED
    record.error_code = error_code
    record.lease_owner = record.lease_token = None
    record.lease_expires_at = None
    if not terminal:
        record.next_attempt_at = _now() + timedelta(
            seconds=next_attempt_delay(record.attempt)
        )
    await session.commit()
    await session.refresh(record)
    return record
