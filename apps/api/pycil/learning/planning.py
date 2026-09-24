"""Session admission, depth-keyed demand, and derived session shape."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from lexi_ai.contracts import PrepareDemand
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.hierarchy.application.subtree import resolve_sense_ids
from pycil.learning.fsrs import recall
from pycil.learning.fsrs_wrapper import elapsed_days
from pycil.learning.models import UserLearningSettings
from pycil.learning.session_store import AdmittedSense
from pycil.policy.policy import (
    ASSESSMENT_FLOOR,
    NEW_WORD_FLOOR,
    sample_requested_level,
)
from pycil.policy.sense_state import SenseStatus, UserSenseStats
from pycil.product_config import system_config

_STATS_SQL = text(
    """
    SELECT sense_id, stability, difficulty, mastery, interval_days,
           last_review_date, next_review_date, review_count, lapse_count,
           status, depth_level, depth_streak, created_at, updated_at, user_id
    FROM user_sense_stats
    WHERE user_id = :user_id AND sense_id = ANY(CAST(:sense_ids AS bigint[]))
    """
)


@dataclass(frozen=True)
class DueCandidate:
    """A scheduled sense that is due for review, ranked for admission."""

    sense_id: int
    mastery: int
    depth_level: int
    recall: float
    overdue_seconds: float


async def load_candidates(
    session: AsyncSession,
    user_id: UUID,
    node_id: UUID,
    now: datetime,
) -> tuple[list[DueCandidate], list[int]]:
    """Return due and new senses in the authorized node scope."""
    sense_ids = await resolve_sense_ids(session, node_id, viewer_id=user_id)
    if not sense_ids:
        return [], []

    rows = await session.execute(
        _STATS_SQL, {"user_id": str(user_id), "sense_ids": sense_ids}
    )
    stats = {
        int(row.sense_id): UserSenseStats.model_validate(row._mapping) for row in rows
    }

    due: list[DueCandidate] = []
    new: list[int] = []
    for sense_id in sense_ids:
        state = stats.get(sense_id)
        if state is None or state.status == SenseStatus.new:
            new.append(sense_id)
        elif state.status == SenseStatus.scheduled:
            if state.next_review_date is not None and state.next_review_date <= now:
                recall_probability = recall(
                    state.stability, elapsed_days(state.last_review_date, now)
                )
                overdue = (now - state.next_review_date).total_seconds()
                due.append(
                    DueCandidate(
                        sense_id=sense_id,
                        mastery=state.mastery,
                        depth_level=state.depth_level,
                        recall=recall_probability,
                        overdue_seconds=overdue,
                    )
                )

    due.sort(key=lambda candidate: (candidate.recall, -candidate.overdue_seconds))
    return due, new


@dataclass(frozen=True)
class SessionSettings:
    target_words_per_session: int
    max_questions_per_round: int


@dataclass(frozen=True)
class PlanResult:
    admitted: list[AdmittedSense]
    demands: list[PrepareDemand]


def default_session_settings() -> SessionSettings:
    """The product defaults for session shape, owned by ``config/config.yaml``.

    Read through a function rather than a module constant so importing this
    module does not parse the configuration file, and so a learner with no
    settings row and a learner who reset theirs resolve to the same values.
    """
    learning = system_config.learning
    return SessionSettings(
        target_words_per_session=learning.max_words_per_session,
        max_questions_per_round=learning.max_questions_per_round,
    )


async def settings_for_user(session: AsyncSession, user_id: UUID) -> SessionSettings:
    """Read the learner's effective two-number session shape."""
    row = await session.get(UserLearningSettings, user_id)
    if row is None:
        return default_session_settings()
    return SessionSettings(
        target_words_per_session=max(1, row.target_words_per_session),
        max_questions_per_round=max(1, row.max_questions_per_round),
    )


async def save_settings(
    session: AsyncSession,
    user_id: UUID,
    *,
    target_words_per_session: int,
    max_questions_per_round: int,
    now: datetime | None = None,
) -> SessionSettings:
    """Persist the learner's two session-shape settings with an upsert."""
    moment = now if now is not None else datetime.now(UTC)
    statement = pg_insert(UserLearningSettings).values(
        user_id=user_id,
        target_words_per_session=target_words_per_session,
        max_questions_per_round=max_questions_per_round,
        updated_at=moment,
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "target_words_per_session": statement.excluded.target_words_per_session,
                "max_questions_per_round": statement.excluded.max_questions_per_round,
                "updated_at": statement.excluded.updated_at,
            },
        )
    )
    await session.commit()
    return SessionSettings(
        target_words_per_session=target_words_per_session,
        max_questions_per_round=max_questions_per_round,
    )


def _slot_split(target: int, due_available: int) -> tuple[int, int]:
    """Return ``(new_slots, due_slots)`` while reserving the new-word floor."""
    new_slots = min(max(NEW_WORD_FLOOR, target - due_available), target)
    return new_slots, target - new_slots


def _admit(
    due: list[DueCandidate],
    new: list[int],
    target: int,
    new_slots: int,
    due_slots: int,
) -> tuple[list[DueCandidate], list[int]]:
    """Admit due-first up to slots, then backfill any shortfall."""
    due_take = min(due_slots, len(due))
    new_take = min(new_slots, len(new))
    capacity = target - due_take - new_take
    extra_due = min(capacity, len(due) - due_take)
    due_take += extra_due
    capacity -= extra_due
    new_take += min(capacity, len(new) - new_take)
    return due[:due_take], new[:new_take]


def _requirements(
    admitted_due: list[DueCandidate],
    admitted_new: list[int],
    rng: random.Random,
) -> list[AdmittedSense]:
    """Build exactly one assessment requirement per admitted sense."""
    admitted = [
        AdmittedSense(
            sense_id=candidate.sense_id,
            purpose="due",
            requested_level=sample_requested_level(candidate.depth_level, rng),
        )
        for candidate in admitted_due
    ]
    admitted.extend(
        AdmittedSense(sense_id=sense_id, purpose="new", requested_level=ASSESSMENT_FLOOR)
        for sense_id in admitted_new
    )
    return admitted


def _demands(admitted: list[AdmittedSense]) -> list[PrepareDemand]:
    """Request one library item for each admitted sense and sampled level."""
    return [
        PrepareDemand(sense_id=item.sense_id, difficulty_level=item.requested_level)
        for item in admitted
    ]


async def plan_session(
    session: AsyncSession,
    user_id: UUID,
    node_id: UUID,
    now: datetime,
    settings: SessionSettings,
    rng: random.Random | None = None,
) -> PlanResult:
    """Select senses once and build one graded demand for each."""
    picker = rng if rng is not None else random.Random()
    due, new = await load_candidates(session, user_id, node_id, now)
    target = settings.target_words_per_session
    new_slots, due_slots = _slot_split(target, len(due))
    admitted_due, admitted_new = _admit(due, new, target, new_slots, due_slots)
    admitted = _requirements(admitted_due, admitted_new, picker)
    return PlanResult(admitted=admitted, demands=_demands(admitted))
