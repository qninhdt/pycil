"""Dashboard read model: the learner's own progress across every deck they own.

Extracted from an 80-line body inside `GET /learning/dashboard`. The route had four
aggregate queries, a seven-day forecast built in Python, and the
"continue where you left off" resolution with its fallback — none of it reachable
from a test except through HTTP, and none of it reusable.

Node-scoped stats live in `hierarchy/stats.py`; this module is deliberately separate
because these figures are scoped to the *learner*, not to a node, and are the only
ones that answer "what should I do next".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.hierarchy.infra.models import Node, NodeType
from pycil.learning.models import ReviewLog
from pycil.policy.sense_state import SenseStatus, UserSenseStats

# Days of due-count forecast the dashboard renders, today inclusive.
FORECAST_DAYS = 7


@dataclass(frozen=True)
class ForecastDay:
    day: date
    due_count: int


@dataclass(frozen=True)
class ResumeTarget:
    """Which deck "continue where you left off" should open."""

    node_id: UUID
    deck_title: str
    remaining_count: int


@dataclass(frozen=True)
class DashboardStats:
    total_learned_words: int
    due_today_count: int
    mastery_percentage: float
    forecast: list[ForecastDay]
    resume: ResumeTarget | None


def _engaged():
    """The durable learning boundary: FSRS has scheduled the sense."""
    return UserSenseStats.status == SenseStatus.scheduled


async def load(session: AsyncSession, user_id: UUID, now: datetime) -> DashboardStats:
    """Every figure the dashboard shows, for one learner."""
    engaged = _engaged()

    total_learned = (
        await session.execute(
            select(func.count(UserSenseStats.sense_id)).where(
                UserSenseStats.user_id == user_id, engaged
            )
        )
    ).scalar() or 0

    due_today = (
        await session.execute(
            select(func.count(UserSenseStats.sense_id)).where(
                UserSenseStats.user_id == user_id,
                UserSenseStats.status == SenseStatus.scheduled,
                UserSenseStats.next_review_date <= now,
            )
        )
    ).scalar() or 0

    average = (
        await session.execute(
            select(func.avg(UserSenseStats.mastery)).where(
                UserSenseStats.user_id == user_id, engaged
            )
        )
    ).scalar()

    return DashboardStats(
        total_learned_words=int(total_learned),
        due_today_count=int(due_today),
        mastery_percentage=round(float(average), 1) if average is not None else 0.0,
        forecast=await _forecast(session, user_id, now),
        resume=await _resume_target(session, user_id, now, due_today=int(due_today)),
    )


async def _forecast(
    session: AsyncSession, user_id: UUID, now: datetime
) -> list[ForecastDay]:
    """Due counts for the next `FORECAST_DAYS` days, overdue folded into today.

    Bucketed in Python, deliberately, but over a bounded row set.

    The route loaded every scheduled row the learner had, so the cost grew with
    everything they had ever studied even though the answer spans seven days. The
    `WHERE` clause now bounds it to rows that can land in a bucket.

    Bucketing itself stays in Python rather than becoming `GROUP BY date(...)`.
    `date()` on a `timestamptz` resolves in the *session's* timezone: measured on this
    database, `2026-08-05 23:30+00` is 2026-08-05 under UTC and 2026-08-06 under
    Asia/Ho_Chi_Minh. Moving the bucketing into SQL would therefore make the forecast
    depend on a connection setting, silently shifting a near-midnight sense by a day.
    The comparison against `now` here uses the same instant the caller passed, which
    is what the rest of the module already agrees on.
    """
    today = now.date()
    counts: dict[date, int] = {
        today + timedelta(days=i): 0 for i in range(FORECAST_DAYS)
    }
    # One day of slack on the upper bound so a row whose local date falls inside the
    # window is never excluded by the instant comparison.
    horizon = now + timedelta(days=FORECAST_DAYS)

    due_dates = await session.scalars(
        select(UserSenseStats.next_review_date).where(
            UserSenseStats.user_id == user_id,
            UserSenseStats.next_review_date.is_not(None),
            UserSenseStats.next_review_date < horizon,
        )
    )
    for next_review in due_dates:
        if next_review is None:
            continue
        day = next_review.date()
        if day <= today:
            # Overdue senses are work for today, not history the learner can act on.
            counts[today] += 1
        elif day in counts:
            counts[day] += 1

    return [
        ForecastDay(day=day, due_count=count) for day, count in sorted(counts.items())
    ]


async def _resume_target(
    session: AsyncSession, user_id: UUID, now: datetime, *, due_today: int
) -> ResumeTarget | None:
    """The deck the learner last reviewed in, or their first deck as a fallback.

    The fallback is used only for a learner who has never reviewed anything.
    """
    recent_node_id = (
        await session.execute(
            select(ReviewLog.node_id)
            .where(ReviewLog.user_id == user_id, ReviewLog.node_id.is_not(None))
            .order_by(ReviewLog.reviewed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if recent_node_id is not None:
        node = await session.get(Node, recent_node_id)
        if node is not None:
            return ResumeTarget(
                node_id=node.id, deck_title=node.name, remaining_count=due_today
            )

    first_deck = (
        await session.scalars(
            select(Node)
            .where(Node.author_id == user_id, Node.type == NodeType.DECK)
            # Ordered so the fallback is at least stable across requests; without it
            # two loads could offer two different decks.
            .order_by(Node.created_at, Node.id)
            .limit(1)
        )
    ).first()
    if first_deck is None:
        return None
    return ResumeTarget(
        node_id=first_deck.id,
        deck_title=first_deck.name,
        remaining_count=due_today,
    )
