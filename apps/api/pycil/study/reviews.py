from datetime import UTC, datetime

from lexi_ai import Sense

from pycil.account.lifecycle import require_user
from pycil.database import transaction_lock
from pycil.http import Problem
from pycil.study.fsrs import mastery, next_state
from pycil.study.models import Rating, ReviewLog, SenseMemory


def projection(event):
    return {
        "sense_id": event.sense_id,
        "rating": event.rating,
        "applied": event.applied,
        "accepted_at": event.accepted_at,
        "mastery_after": event.mastery_after,
        "due_after": event.due_after,
    }


async def review(session, user_id, data, event_key, config):
    async with session.begin():
        await transaction_lock(session, f"review-event:{user_id}:{event_key}")
        await require_user(session, user_id)
        previous = await session.get(ReviewLog, (user_id, event_key))
        if previous is not None:
            if (previous.sense_id, previous.rating) != (data.sense_id, data.rating):
                raise Problem(409, "review_event_conflict")
            return projection(previous)
        await transaction_lock(session, f"memory:{user_id}:{data.sense_id}")
        if await session.get(Sense, data.sense_id) is None:
            raise Problem(422, "sense_not_found")
        memory = await session.get(SenseMemory, (user_id, data.sense_id))
        now = datetime.now(UTC)
        applied = memory is None or memory.due_at <= now or data.rating is Rating.AGAIN
        if applied:
            stability, difficulty, due = next_state(memory, data.rating, now, config)
            is_new = memory is None
            if is_new:
                memory = SenseMemory(
                    user_id=user_id,
                    sense_id=data.sense_id,
                    review_count=0,
                    lapse_count=0,
                    created_at=now,
                )
                session.add(memory)
            memory.stability, memory.difficulty, memory.due_at = stability, difficulty, due
            memory.last_review_at = memory.updated_at = now
            memory.last_rating = data.rating
            memory.review_count += 1
            memory.lapse_count += int(not is_new and data.rating is Rating.AGAIN)
        event = ReviewLog(
            user_id=user_id,
            event_key=event_key,
            sense_id=data.sense_id,
            rating=data.rating,
            accepted_at=now,
            applied=applied,
            mastery_after=mastery(memory.stability, config),
            due_after=memory.due_at,
        )
        session.add(event)
        await session.flush()
        return projection(event)
