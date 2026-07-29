"""Session planner: admit senses, build per-sense requirements, aggregate demand.

Admits up to ``target_words_per_session`` unique senses (due-first with the
``NEW_WORD_FLOOR`` reserved), constructs each admitted sense's requirements (new:
exposure + N level-1 checkpoints; due: N checkpoints with independently
mastery-sampled requested levels), and aggregates the ``prepare`` demand.

This module is DB-read + pure: it never blocks on ``prepare``.  It returns the
admitted set (for ``session_store.create``) and the demand list; the router
enqueues the best-effort, quota-gated warm-up (executed on the worker, which owns
the provider-enabled ``prepare_questions``).  A transient not-yet-warm sense
defers via the existing generation-pending flow rather than blocking session
creation (F7).
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from lexi_ai.contracts import PrepareDemand
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.learning import session_queue
from pycil.learning.models import UserLearningSettings
from pycil.learning.policy import (
    ASSESSMENT_FLOOR,
    DEFAULT_MAX_QUESTIONS_PER_ROUND,
    DEFAULT_TARGET_WORDS_PER_SESSION,
    NEW_WORD_FLOOR,
    REQUIRED_CHECKPOINTS,
    sample_requested_level,
)
from pycil.learning.session_store import AdmittedSense


@dataclass(frozen=True)
class SessionSettings:
    target_words_per_session: int
    max_questions_per_round: int


@dataclass(frozen=True)
class PlanResult:
    admitted: list[AdmittedSense]
    demands: list[PrepareDemand]


DEFAULT_SESSION_SETTINGS = SessionSettings(
    target_words_per_session=DEFAULT_TARGET_WORDS_PER_SESSION,
    max_questions_per_round=DEFAULT_MAX_QUESTIONS_PER_ROUND,
)


async def settings_for_user(session: AsyncSession, user_id: UUID) -> SessionSettings:
    """The learner's session shape, or the policy defaults when they have none.

    Session shape belongs to the learner rather than to a deck: the same person
    wants the same session length whichever deck they open, and holding it per deck
    meant a client showing "your settings" had to walk the node tree to find every
    deck first.

    An absent row is the normal state, not a missing one. Signing up writes nothing,
    and a learner who never opens Settings keeps whatever the policy defaults say —
    which is also how a default can be changed for everyone who never overrode it.
    """
    row = await session.get(UserLearningSettings, user_id)
    if row is None:
        return DEFAULT_SESSION_SETTINGS
    # Clamped on read as well as written under a CHECK constraint: the planner
    # divides work by these, so a zero arriving from any future writer would produce
    # a session with nothing in it rather than an error.
    return SessionSettings(
        target_words_per_session=max(1, row.target_words_per_session),
        max_questions_per_round=max(1, row.max_questions_per_round),
    )


def _slot_split(target: int, due_available: int) -> tuple[int, int]:
    """Return ``(new_slots, due_slots)`` per spec, reserving the new-word floor."""
    new_slots = max(NEW_WORD_FLOOR, target - due_available)
    new_slots = min(new_slots, target)
    due_slots = target - new_slots
    return new_slots, due_slots


def _admit(
    due: list[session_queue.DueCandidate],
    new: list[int],
    target: int,
    new_slots: int,
    due_slots: int,
) -> tuple[list[session_queue.DueCandidate], list[int]]:
    """Admit due-first up to slots, then backfill the shortfall (due first)."""
    due_take = min(due_slots, len(due))
    new_take = min(new_slots, len(new))
    capacity = target - (due_take + new_take)
    extra_due = min(capacity, len(due) - due_take)
    due_take += extra_due
    capacity -= extra_due
    extra_new = min(capacity, len(new) - new_take)
    new_take += extra_new
    return due[:due_take], new[:new_take]


def _requirements(
    admitted_due: list[session_queue.DueCandidate],
    admitted_new: list[int],
    rng: random.Random,
) -> list[AdmittedSense]:
    """Build per-sense requirements (requested levels persisted at plan time)."""
    admitted: list[AdmittedSense] = []
    for candidate in admitted_due:
        # Independently sample each checkpoint's requested level at PLAN time so
        # retries preserve the original requested level per checkpoint.
        levels = [
            sample_requested_level(candidate.mastery, rng)
            for _ in range(REQUIRED_CHECKPOINTS)
        ]
        admitted.append(AdmittedSense(candidate.sense_id, "due", levels))
    for sense_id in admitted_new:
        # Acquisition: exposure (implied by purpose='new') + N level-1 checkpoints
        # (assessment floor; never falls back).
        admitted.append(
            AdmittedSense(sense_id, "new", [ASSESSMENT_FLOOR] * REQUIRED_CHECKPOINTS)
        )
    return admitted


def _demands(admitted: list[AdmittedSense]) -> list[PrepareDemand]:
    """Aggregate ``prepare`` demand per ``(sense_id, level)`` across requirements."""
    counter: Counter[tuple[int, int]] = Counter()
    for item in admitted:
        for level in item.requested_levels:
            counter[(item.sense_id, level)] += 1
    return [
        PrepareDemand(
            sense_id=str(sense_id), difficulty_level=level, expected_count=count
        )
        for (sense_id, level), count in counter.items()
    ]


async def plan_session(
    session: AsyncSession,
    user_id: UUID,
    node_id: UUID,
    now: datetime,
    settings: SessionSettings,
    rng: random.Random | None = None,
) -> PlanResult:
    """Plan one session: select candidates, admit, build requirements + demands."""
    picker = rng if rng is not None else random.Random()
    due, new = await session_queue.load_candidates(session, user_id, node_id, now)
    target = settings.target_words_per_session
    new_slots, due_slots = _slot_split(target, len(due))
    admitted_due, admitted_new = _admit(due, new, target, new_slots, due_slots)
    admitted = _requirements(admitted_due, admitted_new, picker)
    return PlanResult(admitted=admitted, demands=_demands(admitted))
