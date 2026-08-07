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
