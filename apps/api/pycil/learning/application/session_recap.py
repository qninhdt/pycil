"""Durable session recap: write it at completion, read it after Redis is gone.

``end_session`` deletes the whole Redis namespace as soon as a session completes,
so the live state a recap screen needs stops existing at exactly the moment the
learner wants to look at it. This module persists the counts just before that
deletion and serves them afterwards.

Counts only, on purpose. FSRS effects stay authoritative in ``review_log`` and
``user_sense_stats``; nothing here is ever read back into the domain, so it cannot
drift into a competing source of truth.
"""

from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import Integer, case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.learning.infra import session_store
from pycil.learning.infra.models import Response, SessionSummary


async def answer_counts(
    session: AsyncSession, user_id: UUID, session_id: str
) -> tuple[int, int]:
    """Answered and correct counts from the durable rows, never from Redis.

    ``is_correct`` is nullable while a grade is pending, and a pending answer counts
    as answered but not yet correct.

    The ``COALESCE`` is the load-bearing part, not the ``CASE``: ``SUM`` already skips
    NULLs, but it returns NULL rather than 0 over a set with no non-NULL values — so a
    learner who starts a session and leaves, or whose only answer is still being
    graded, would reach ``int(None)`` and get a 500 instead of a recap. The ``CASE``
    is kept because it states the intent at the point of the query: only a verdict of
    exactly ``true`` counts as correct.
    """
    row = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(
                    func.sum(
                        case((Response.is_correct.is_(True), 1), else_=0).cast(Integer)
                    ),
                    0,
                ),
            ).where(Response.user_id == user_id, Response.session_id == session_id)
        )
    ).one()
    return int(row[0]), int(row[1])


async def persist(
    session: AsyncSession,
    redis: Redis,
    session_id: str,
    *,
    user_id: UUID,
    node_id: UUID,
) -> None:
    """Write the recap for a completed session. Idempotent.

    Called before ``end_session``, while the Redis state still exists. Both
    ``/next`` and ``/answers`` can reach the completion predicate for the same
    session, so the insert is an upsert on ``(user_id, session_id)`` rather than a
    plain insert that would raise on the second caller.
    """
    admitted = await session_store.get_admitted(redis, session_id)
    completed = 0
    exhausted = 0
    for sense_id in admitted:
        progress = await session_store.get_progress(redis, session_id, sense_id)
        if progress is None:
            continue
        if progress.terminal_reason == "retries_exhausted":
            exhausted += 1
        elif progress.terminal:
            completed += 1
    meta = await session_store.get_meta(redis, session_id)
    answers_total, answers_correct = await answer_counts(session, user_id, session_id)

    statement = insert(SessionSummary).values(
        user_id=user_id,
        session_id=session_id,
        node_id=node_id,
        senses_admitted=len(admitted),
        senses_completed=completed,
        senses_exhausted=exhausted,
        answers_total=answers_total,
        answers_correct=answers_correct,
        # round_index is 0-based and counts boundaries crossed, so a session that
        # never left the first round used one.
        rounds_used=(meta.round_index + 1) if meta is not None else 0,
    )
    await session.execute(
        statement.on_conflict_do_update(
            constraint="uq_session_summary",
            set_={
                "senses_admitted": statement.excluded.senses_admitted,
                "senses_completed": statement.excluded.senses_completed,
                "senses_exhausted": statement.excluded.senses_exhausted,
                "answers_total": statement.excluded.answers_total,
                "answers_correct": statement.excluded.answers_correct,
                "rounds_used": statement.excluded.rounds_used,
            },
        )
    )
    await session.commit()


async def load(
    session: AsyncSession, user_id: UUID, session_id: str
) -> SessionSummary | None:
    return (
        await session.execute(
            select(SessionSummary).where(
                SessionSummary.user_id == user_id,
                SessionSummary.session_id == session_id,
            )
        )
    ).scalars().first()
