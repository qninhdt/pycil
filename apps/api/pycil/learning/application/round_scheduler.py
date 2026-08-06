"""Round scheduler: pick the next eligible (sense, requirement) per round.

Decides WHICH sense/requirement to serve next (the resolver picks the concrete
question at delivery, Phase 2/8).  A round is a variable-size wave capped at
``max_questions_per_round``, filled by the spec priority order:

    1. eligible retries        (failed checkpoint, waited >= 1 round)
    2. due-review checkpoints  (retention)
    3. acquisition checkpoints (level 1, for an already-exposed sense)
    4. new exposures           (level 0)

Round rules: a sense appears at most once per round (``last_round_used``); a retry
waits >= 1 round (``open_failed_round < current_round``); a sense mid-pending-grade
(``awaiting_grade``) or terminal is never eligible.  Unservable requirements are
deferred by the router (resolver ``None`` -> try the next candidate), and a round
with no servable item ends the session cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.learning.infra import session_store
from pycil.learning.infra.models import GradeStatus, Response
from pycil.learning.infra.session_store import SenseProgress
from pycil.policy.policy import MAX_RETRIES_PER_CHECKPOINT, REQUIRED_CHECKPOINTS

# Priority tiers (lower runs first).
_TIER_RETRY = 1
_TIER_DUE = 2
_TIER_ACQUISITION = 3
_TIER_EXPOSURE = 4


@dataclass(frozen=True)
class Requirement:
    """A logical unit to serve for a sense (not a concrete question yet)."""

    sense_id: int
    kind: str  # "exposure" | "checkpoint"
    requested_level: int  # 0 for exposure
    is_retry: bool
    checkpoint_index: int  # -1 for exposure
    tier: int


def eligible_requirement(
    purpose: str,
    progress: SenseProgress,
    current_round: int,
    *,
    required_checkpoints: int = REQUIRED_CHECKPOINTS,
    max_retries: int = MAX_RETRIES_PER_CHECKPOINT,
) -> Requirement | None:
    """Return the sense's eligible requirement this round, or ``None``.

    Pure over Redis-loaded progress so it is directly unit-testable.
    """
    if progress.terminal or progress.awaiting_grade:
        return None
    if progress.last_round_used == current_round:
        return None

    # Tier 1: an open retry, eligible only after waiting >= 1 round.
    if progress.open_checkpoint is not None:
        if (
            progress.open_failed_round is not None
            and progress.open_failed_round < current_round
            and progress.retries_used <= max_retries
            and progress.open_requested_level is not None
        ):
            return Requirement(
                sense_id=progress.sense_id,
                kind="checkpoint",
                requested_level=progress.open_requested_level,
                is_retry=True,
                checkpoint_index=progress.open_checkpoint,
                tier=_TIER_RETRY,
            )
        # Open retry not yet due (still waiting this round) -> not eligible.
        return None

    if purpose == "due":
        if progress.passed < required_checkpoints:
            return Requirement(
                sense_id=progress.sense_id,
                kind="checkpoint",
                requested_level=progress.requested_levels[progress.passed],
                is_retry=False,
                checkpoint_index=progress.passed,
                tier=_TIER_DUE,
            )
        return None

    if purpose == "new":
        if not progress.exposed:
            return Requirement(
                sense_id=progress.sense_id,
                kind="exposure",
                requested_level=0,
                is_retry=False,
                checkpoint_index=-1,
                tier=_TIER_EXPOSURE,
            )
        if progress.passed < required_checkpoints:
            return Requirement(
                sense_id=progress.sense_id,
                kind="checkpoint",
                requested_level=progress.requested_levels[progress.passed],
                is_retry=False,
                checkpoint_index=progress.passed,
                tier=_TIER_ACQUISITION,
            )
        return None

    return None


async def round_candidates(
    redis: Redis, session_id: str, current_round: int
) -> list[Requirement]:
    """Eligible requirements for ``current_round``, in priority-then-sense order.

    Not capacity-capped: the router serves one per ``/next`` and stops when
    ``round_count`` reaches ``max_questions_per_round``; a resolver ``None`` defers
    a candidate (the router tries the next).
    """
    admitted = await session_store.get_admitted(redis, session_id)
    requirements: list[Requirement] = []
    for sense_id, purpose in admitted.items():
        progress = await session_store.get_progress(redis, session_id, sense_id)
        if progress is None:
            continue
        requirement = eligible_requirement(purpose, progress, current_round)
        if requirement is not None:
            requirements.append(requirement)
    requirements.sort(key=lambda r: (r.tier, r.sense_id))
    return requirements


async def has_open_work(redis: Redis, session_id: str) -> bool:
    """True if any admitted sense is still non-terminal (work may remain)."""
    admitted = await session_store.get_admitted(redis, session_id)
    for sense_id in admitted:
        progress = await session_store.get_progress(redis, session_id, sense_id)
        if progress is not None and not progress.terminal:
            return True
    return False


async def has_pending_grade(
    session: AsyncSession, redis: Redis, session_id: str
) -> bool:
    """True if any admitted sense awaits a grade OR a ``responses`` row is pending.

    Combines the Redis advisory flag with the Postgres-authoritative pending
    check so an in-flight llm settle is never treated as finished.
    """
    admitted = await session_store.get_admitted(redis, session_id)
    for sense_id in admitted:
        progress = await session_store.get_progress(redis, session_id, sense_id)
        if progress is not None and progress.awaiting_grade:
            return True
    pending_count = await session.scalar(
        select(func.count(Response.id)).where(
            Response.session_id == session_id,
            Response.grade_status == GradeStatus.pending,
        )
    )
    return bool(pending_count)


async def session_complete(
    session: AsyncSession, redis: Redis, session_id: str
) -> bool:
    """The single pending-aware session-end predicate (F12).

    Complete only when every admitted sense is terminal AND no checkpoint is
    awaiting a grade AND no ``responses`` row for the session is still pending.
    Every session-end path routes through this before ``end_session`` deletes the
    Redis namespace, so an in-flight llm settle is never orphaned.
    """
    admitted = await session_store.get_admitted(redis, session_id)
    if not admitted:
        # No admitted set (already ended, or empty plan) — nothing in flight.
        return not await has_pending_grade(session, redis, session_id)
    for sense_id in admitted:
        progress = await session_store.get_progress(redis, session_id, sense_id)
        if progress is None or not progress.terminal:
            return False
    return not await has_pending_grade(session, redis, session_id)
