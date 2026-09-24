"""Owner-scoped job status.

A job receipt is readable only by the learner it belongs to. Another caller
guessing an id gets the same 404 an unknown id gets, so the route never confirms
that someone else's job exists.

The route deliberately requires authentication rather than accepting an anonymous
read: a receipt carries the result reference for one learner's content work, and
there is no product reason for an unauthenticated caller to read one.
"""

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import NotFoundError, error_responses
from pycil.db.redis import get_redis
from pycil.queue.receipts import (
    STATUS_DONE,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    read_receipt,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])

#: What a client may see. Anything else is normalized to `failed` rather than
#: echoed, so an unexpected internal state cannot become a new client contract by
#: accident.
_PUBLIC_STATUS = {
    STATUS_QUEUED: STATUS_QUEUED,
    STATUS_RUNNING: STATUS_RUNNING,
    STATUS_DONE: STATUS_DONE,
    STATUS_FAILED: STATUS_FAILED,
    STATUS_EXPIRED: STATUS_EXPIRED,
}


@router.get("/{job_id}", responses=error_responses(401, 404))
async def get_job(
    job_id: str,
    user: CurrentUser = Depends(current_user),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Return the owner's view of one job receipt."""
    receipt = await read_receipt(redis, job_id)
    if receipt is None or receipt.get("owner_id") != str(user.id):
        # Same response for "no such job" and "not yours": distinguishing them
        # would let a caller enumerate other learners' job ids.
        raise NotFoundError("job_not_found")

    raw_status = receipt.get("status", STATUS_QUEUED)
    return {
        "jobId": receipt.get("id", job_id),
        "kind": receipt.get("kind"),
        "status": _PUBLIC_STATUS.get(raw_status, STATUS_FAILED),
        "result": receipt.get("result"),
        "errorCode": receipt.get("errorCode"),
    }
