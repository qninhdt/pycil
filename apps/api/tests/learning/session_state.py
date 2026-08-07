"""Session-state setup helpers built on the projection the app actually calls.

Tests need to put a sense into a known state — one checkpoint passed, a retry
open, retries burnt — before asserting on something else. Several used to reach
for the narrow writers (`pass_checkpoint`, `open_retry`) that no production path
calls: `apply_checkpoint_projection` is the single writer, and it is a strict
superset of both (it additionally clears `awaiting_grade`, records the projection
id for replay dedup, and settles `score` on first grade).

Setup that goes through a different writer than production drifts silently: the
state a test builds stops being a state the app can produce, and an assertion
about it stops meaning anything. These wrappers keep the arrange step on the real
writer while reading as plainly as the ones they replace.

Each call passes a fresh `response_id`, because the projection is idempotent per
id — reusing one would make a second call a no-op rather than a second
checkpoint.
"""

from uuid import uuid4

from pycil.learning.infra import session_store
from pycil.policy.policy import MAX_RETRIES_PER_CHECKPOINT, REQUIRED_CHECKPOINTS

# The complete branch derives `passed` from stored state and hardcodes the retry
# reset, so these two are structurally unread. Named rather than inlined so the
# call below states that it is not asserting anything about them.
_UNREAD_ON_COMPLETE = 0


async def mark_exposed(redis, session_id: str, sense_id: int) -> None:
    """Set the `exposed` flag alone, as a precondition rather than an event.

    Deliberately NOT routed through `reserve_round_delivery`, which is the only
    production writer of this flag. That call additionally stamps
    `last_round_used` and spends a round slot, and `eligible_requirement`
    refuses a sense whose `last_round_used == current_round` — so a test that
    only wants "this sense has already been seen" would get a sense that is
    also ineligible this round, which is a different fixture than it asked for.
    Measured: the same sense reads as a live tier-3 requirement after this
    helper and as `None` after a real reservation.

    So this writes the flag directly. That is honest for an arrange step whose
    subject is something else (does acquisition reach FSRS, does the review log
    carry a deck); a test whose subject IS delivery should call
    `reserve_round_delivery` and assert on what it really does.
    """
    key = session_store._sense_key(session_id, sense_id)
    await redis.hset(key, "exposed", "1")
    await redis.expire(key, session_store._TTL_SECONDS)


async def exclude_question(redis, session_id: str, sense_id: int, question_id: int) -> None:
    """Add one served question id to a sense's excluded set.

    Production adds these inside `reserve_round_delivery`'s transaction, never on
    its own. Written directly here for the same reason as `mark_exposed`: the one
    caller is asserting that `excluded_ids` parses its members back as an int
    frozenset, and routing it through a reservation would drag in a round slot
    and a question binding that the assertion does not care about.
    """
    key = session_store._excluded_key(session_id, sense_id)
    await redis.sadd(key, question_id)
    await redis.expire(key, session_store._TTL_SECONDS)


async def pass_checkpoint(
    redis,
    session_id: str,
    sense_id: int,
    *,
    required_checkpoints: int = REQUIRED_CHECKPOINTS,
) -> bool:
    """Pass one checkpoint. Terminal (`completed`) once `passed` reaches N."""
    return await session_store.apply_checkpoint_projection(
        redis,
        session_id,
        sense_id,
        response_id=uuid4(),
        state_action="complete",
        requested_level=_UNREAD_ON_COMPLETE,
        retries_used=_UNREAD_ON_COMPLETE,
        failed_round=_UNREAD_ON_COMPLETE,
        max_retries=MAX_RETRIES_PER_CHECKPOINT,
        grade_due=None,
        fsrs_applied=False,
        required_checkpoints=required_checkpoints,
    )


async def open_retry(
    redis,
    session_id: str,
    sense_id: int,
    *,
    requested_level: int,
    retries_used: int,
    failed_round: int,
    max_retries: int = MAX_RETRIES_PER_CHECKPOINT,
) -> bool:
    """Open a retry on the current checkpoint.

    `retries_used` is caller-computed, matching production: the sense goes
    terminal (`retries_exhausted`) when it exceeds `max_retries`.
    """
    return await session_store.apply_checkpoint_projection(
        redis,
        session_id,
        sense_id,
        response_id=uuid4(),
        state_action="open_retry",
        requested_level=requested_level,
        retries_used=retries_used,
        failed_round=failed_round,
        max_retries=max_retries,
        grade_due=None,
        fsrs_applied=False,
    )
