"""Candidate pool: load due-review and new senses for session planning.

Re-homed from the old single-queue builder.  The session planner (``planning``)
consumes these helpers to admit senses; this module only loads + classifies +
ranks candidates.  The buried filter and the canonical subtree scope are reused
verbatim from the prior implementation.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from shared.fsrs import recall
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.hierarchy.subtree import resolve_sense_ids
from pycil.learning.fsrs_wrapper import elapsed_days
from pycil.learning.models import SenseStatus, UserSenseStats

_STATS_SQL = text(
    """
    SELECT sense_id, stability, difficulty, mastery, interval_days,
           last_review_date, next_review_date, review_count, lapse_count,
           status, buried_until, created_at, updated_at, user_id
    FROM user_sense_stats
    WHERE user_id = :user_id AND sense_id = ANY(CAST(:sense_ids AS bigint[]))
    """
)


@dataclass(frozen=True)
class DueCandidate:
    """A scheduled sense that is due for review, ranked for admission."""

    sense_id: int
    mastery: int
    recall: float
    overdue_seconds: float


async def load_candidates(
    session: AsyncSession,
    user_id: UUID,
    node_id: UUID,
    now: datetime,
) -> tuple[list[DueCandidate], list[int]]:
    """Return ``(due, new)`` candidates in the authorized node scope.

    ``due``: ``status='scheduled'`` AND ``next_review_date <= now`` AND not buried,
    ranked by retrievability ascending (weakest first), then most-overdue.
    ``new``: no stats row or ``status='new'``, not buried (in ``sense_id`` order).
    Not-due scheduled senses are excluded.
    """
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
    for sid in sense_ids:
        st = stats.get(sid)
        if st is not None and st.buried_until is not None and st.buried_until > now:
            continue
        if st is None or st.status == SenseStatus.new:
            new.append(sid)
        elif st.status == SenseStatus.scheduled:
            if st.next_review_date is not None and st.next_review_date <= now:
                r = recall(st.stability, elapsed_days(st.last_review_date, now))
                overdue = (now - st.next_review_date).total_seconds()
                due.append(
                    DueCandidate(
                        sense_id=sid, mastery=st.mastery, recall=r, overdue_seconds=overdue
                    )
                )
            # A scheduled-but-not-due sense is intentionally excluded this session.

    due.sort(key=lambda c: (c.recall, -c.overdue_seconds))
    return due, new
