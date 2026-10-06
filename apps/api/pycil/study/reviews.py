"""Atomic ordered batches. Immutable receipts are the only replay authority."""

import hashlib
import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from lexi_ai.contract import Sense
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from pycil.account.lifecycle import require_user
from pycil.account.models import User
from pycil.account.schemas import preferences
from pycil.database import transaction_lock
from pycil.http import Problem
from pycil.study.fsrs import next_state
from pycil.study.models import DailyActivity, Rating, ReviewReceipt, UserSense
from pycil.study.schemas import BatchResult


def request_hash(data):
    encoded = json.dumps(
        data.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def review(session, user_id, data, event_key, config):
    if len(data.results) > config.learning.limits.max_review_batch:
        raise Problem(422, "review_batch_too_large")
    digest = request_hash(data)
    async with session.begin():
        await transaction_lock(session, f"review-event:{user_id}:{event_key}")
        await require_user(session, user_id)
        previous = await session.get(ReviewReceipt, (user_id, event_key))
        if previous is not None:
            if previous.request_hash != digest:
                raise Problem(409, "review_batch_conflict")
            return previous.result
        identifiers = sorted(r.sense_id for r in data.results)
        found = set(
            (await session.scalars(select(Sense.id).where(Sense.id.in_(identifiers)))).all()
        )
        if found != set(identifiers):
            raise Problem(422, "sense_not_found")
        for identifier in identifiers:
            await transaction_lock(session, f"memory:{user_id}:{identifier}")
        memories = {
            m.sense_id: m
            for m in (
                await session.scalars(
                    select(UserSense).where(
                        UserSense.user_id == user_id, UserSense.sense_id.in_(identifiers)
                    )
                )
            ).all()
        }
        saved = await session.scalar(select(User.settings).where(User.id == user_id))
        now = datetime.now(UTC)
        day = now.astimezone(ZoneInfo(preferences(saved, config).timezone)).date()
        results = []
        applied_count = 0
        for item in data.results:
            memory = memories.get(item.sense_id)
            applied = memory is None or memory.due_at <= now or item.rating is Rating.AGAIN
            if applied:
                stability, difficulty, due = next_state(memory, item.rating, now, config)
                is_new = memory is None
                if is_new:
                    memory = UserSense(
                        user_id=user_id,
                        sense_id=item.sense_id,
                        review_count=0,
                        lapse_count=0,
                        created_at=now,
                    )
                    session.add(memory)
                memory.stability, memory.difficulty, memory.due_at = stability, difficulty, due
                memory.last_review_at = memory.updated_at = now
                memory.last_rating = item.rating
                memory.review_count += 1
                memory.lapse_count += int(not is_new and item.rating is Rating.AGAIN)
            applied_count += int(applied)
            results.append(
                {
                    "sense_id": item.sense_id,
                    "rating": item.rating,
                    "applied": applied,
                    "accepted_at": now,
                    "due_after": memory.due_at,
                }
            )
        result = BatchResult(accepted_at=now, activity_day=day, results=results).model_dump(
            mode="json"
        )
        session.add(
            ReviewReceipt(
                user_id=user_id,
                event_key=event_key,
                request_hash=digest,
                accepted_at=now,
                activity_day=day,
                result=result,
            )
        )
        statement = insert(DailyActivity).values(
            user_id=user_id,
            day=day,
            applied_events=applied_count,
            practice_events=len(results) - applied_count,
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[DailyActivity.user_id, DailyActivity.day],
                set_={
                    "applied_events": DailyActivity.applied_events
                    + statement.excluded.applied_events,
                    "practice_events": DailyActivity.practice_events
                    + statement.excluded.practice_events,
                },
            )
        )
        await session.flush()
        return result
