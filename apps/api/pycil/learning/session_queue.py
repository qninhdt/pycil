"""Session queue: rank a deck's senses so the queue is NEVER empty.

Every sense in scope is ranked by retrievability R ascending (lowest R = most
overdue → front). Upcoming cards (high R) still rank, so the queue never empties
even when nothing is strictly due (design §7). New senses are interleaved per a
configured ratio (deck setting overrides, hard fallback 2 new / 10 review).
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from shared.fsrs import recall
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.hierarchy.subtree import resolve_sense_ids
from pycil.learning.fsrs_wrapper import elapsed_days
from pycil.learning.models import UserSenseStats

_DEFAULT_NEW = 2
_DEFAULT_REVIEW = 10


@dataclass
class QueueItem:
    sense_id: int
    mastery: int
    is_new: bool
    recall: float


async def build_queue(
    session: AsyncSession,
    user_id: UUID,
    node_id: UUID,
    now: datetime,
    *,
    new_per_batch: int = _DEFAULT_NEW,
    review_per_batch: int = _DEFAULT_REVIEW,
    limit: int = 20,
) -> list[QueueItem]:
    """Build a queue from the canonical accessible folder/deck/reference scope."""
    sense_ids = await resolve_sense_ids(session, node_id, viewer_id=user_id)
    if not sense_ids:
        return []

    # A PostgreSQL array is a single bind even for a large subtree. Avoid an
    # expanding IN list here because this queue is fed by the same canonical
    # folder/reference set as stats and history.
    stats_rows = await session.execute(
        text(
            """
            SELECT sense_id, stability, difficulty, mastery, interval_days,
                   last_review_date, next_review_date, review_count, lapse_count,
                   status, buried_until, created_at, updated_at, user_id
            FROM user_sense_stats
            WHERE user_id = :user_id AND sense_id = ANY(CAST(:sense_ids AS bigint[]))
            """
        ),
        {"user_id": str(user_id), "sense_ids": sense_ids},
    )
    stats = {
        int(row.sense_id): UserSenseStats.model_validate(row._mapping)
        for row in stats_rows
    }

    reviews: list[QueueItem] = []
    news: list[QueueItem] = []
    for sid in sense_ids:
        st = stats.get(sid)
        if st is not None and st.buried_until is not None and st.buried_until > now:
            continue
        if st is None or st.review_count == 0:
            news.append(QueueItem(sense_id=sid, mastery=0, is_new=True, recall=1.0))
        else:
            r = recall(st.stability, elapsed_days(st.last_review_date, now))
            reviews.append(
                QueueItem(sense_id=sid, mastery=st.mastery, is_new=False, recall=r)
            )

    # Lowest R (most overdue / weakest) first — upcoming cards still included.
    reviews.sort(key=lambda q: q.recall)
    return _interleave(reviews, news, new_per_batch, review_per_batch)[:limit]


def _interleave(
    reviews: list[QueueItem],
    news: list[QueueItem],
    new_per_batch: int,
    review_per_batch: int,
) -> list[QueueItem]:
    """Mix new senses into the review stream per ratio; never drop either pool."""
    out: list[QueueItem] = []
    ri = ni = 0
    while ri < len(reviews) or ni < len(news):
        for _ in range(review_per_batch):
            if ri < len(reviews):
                out.append(reviews[ri])
                ri += 1
        for _ in range(new_per_batch):
            if ni < len(news):
                out.append(news[ni])
                ni += 1
        # If one pool is exhausted, drain the other (queue stays non-empty).
        if ri >= len(reviews) and ni < len(news):
            out.extend(news[ni:])
            break
        if ni >= len(news) and ri < len(reviews):
            out.extend(reviews[ri:])
            break
    return out


def ratio_from_settings(settings: dict | None) -> tuple[int, int]:
    """Read (new, review) per-batch from deck settings; hard fallback default."""
    if not settings:
        return _DEFAULT_NEW, _DEFAULT_REVIEW
    new = int(settings.get("new_per_batch", _DEFAULT_NEW))
    review = int(settings.get("review_per_batch", _DEFAULT_REVIEW))
    return max(0, new), max(1, review)
