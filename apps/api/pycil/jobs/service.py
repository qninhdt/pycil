"""Persistence operations for durable word-generation jobs."""

import unicodedata
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.jobs.models import JobStatus, WordGeneration


def normalize_query(query: str) -> str:
    """Produce a stable lookup key without changing the submitted query."""
    return " ".join(unicodedata.normalize("NFKC", query).casefold().split())


async def create_generation(
    session: AsyncSession, owner_id: UUID, query: str
) -> WordGeneration:
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


async def get_generation(
    session: AsyncSession, job_id: UUID, owner_id: UUID
) -> WordGeneration | None:
    statement = select(WordGeneration).where(
        WordGeneration.id == job_id,
        WordGeneration.owner_id == owner_id,
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def list_queued_generations(session: AsyncSession, limit: int = 100) -> list[WordGeneration]:
    statement = (
        select(WordGeneration)
        .where(WordGeneration.status == JobStatus.QUEUED)
        .order_by(WordGeneration.created_at, WordGeneration.id)
        .limit(limit)
    )
    return list((await session.execute(statement)).scalars())


async def mark_running(session: AsyncSession, job_id: UUID) -> WordGeneration | None:
    record = await session.scalar(
        select(WordGeneration).where(WordGeneration.id == job_id).with_for_update()
    )
    if record is None or record.status != JobStatus.QUEUED:
        return None
    record.status = JobStatus.RUNNING
    record.attempt += 1
    await session.commit()
    await session.refresh(record)
    return record


async def mark_succeeded(
    session: AsyncSession, job_id: UUID, result: dict
) -> WordGeneration | None:
    record = await session.scalar(
        select(WordGeneration).where(WordGeneration.id == job_id).with_for_update()
    )
    if record is None or record.status != JobStatus.RUNNING:
        return None
    record.status = JobStatus.SUCCEEDED
    record.result = result
    record.error_code = None
    await session.commit()
    await session.refresh(record)
    return record


async def mark_failed(
    session: AsyncSession, job_id: UUID, error_code: str
) -> WordGeneration | None:
    record = await session.scalar(
        select(WordGeneration).where(WordGeneration.id == job_id).with_for_update()
    )
    if record is None or record.status != JobStatus.RUNNING:
        return None
    record.status = JobStatus.FAILED
    record.error_code = error_code
    await session.commit()
    await session.refresh(record)
    return record
