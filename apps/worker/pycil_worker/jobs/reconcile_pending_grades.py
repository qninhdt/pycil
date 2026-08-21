"""Re-enqueue durable pending grade rows after a lost enqueue or stale lease."""

from datetime import UTC, datetime, timedelta

from pycil.learning.infra.models import GradeStatus, Response
from shared.tasks.contract import JOB_NAME_GRADE_ANSWER_V1
from sqlalchemy import or_, select, update

from pycil_worker.context import ReadyWorkerContext

# A pending answer is abandoned after this long and its text is discarded.
EXPIRY_HOURS = 24

# ...unless a worker is actively grading it, in which case the lease protects the
# text. That protection cannot be unconditional: a worker that crashes mid-LLM-call
# never advances `answered_at`, so this sweep re-leases the row on every pass and the
# 24h purge could never reach it — unbounded LLM spend on a single response. This is
# the ceiling that ignores the lease entirely.
HARD_CEILING_HOURS = 48

REQUEUE_BATCH = 100


async def reconcile_pending_grades(ctx: ReadyWorkerContext) -> dict:
    """Bounded outbox sweep; terminal rows and active leases are never requeued."""
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        now = datetime.now(UTC)

        # Pass 1: the ordinary expiry, now lease-aware.
        #
        # It used to purge on `answered_at` alone, so it nulled `raw_answer` out from
        # under a live grading lease — destroying the text a worker was already
        # paying an LLM to judge, and leaving `apply_verdict` with nothing to apply.
        # The requeue query below has always excluded active leases; the purge simply
        # did not, and the two disagreed about what "in flight" means.
        purged = await session.execute(
            update(Response)
            .where(
                Response.grade_status == GradeStatus.pending,
                Response.raw_answer.is_not(None),
                Response.answered_at < now - timedelta(hours=EXPIRY_HOURS),
                or_(
                    Response.grading_lease_expires_at.is_(None),
                    Response.grading_lease_expires_at <= now,
                ),
            )
            .values(
                grade_status=GradeStatus.expired,
                raw_answer=None,
                grading_lease_owner=None,
                grading_lease_expires_at=None,
            )
        )

        # Pass 2: the hard ceiling. Deliberately blind to the lease, so a row whose
        # lease is renewed forever by a crash-looping worker still terminates.
        # Without this, pass 1's new lease condition would introduce exactly the
        # starvation it was added to avoid.
        starved = await session.execute(
            update(Response)
            .where(
                Response.grade_status == GradeStatus.pending,
                Response.raw_answer.is_not(None),
                Response.answered_at < now - timedelta(hours=HARD_CEILING_HOURS),
            )
            .values(
                grade_status=GradeStatus.expired,
                raw_answer=None,
                grading_lease_owner=None,
                grading_lease_expires_at=None,
            )
        )

        rows = (
            (
                await session.execute(
                    select(Response)
                    .where(
                        Response.grade_status == GradeStatus.pending,
                        Response.raw_answer.is_not(None),
                        or_(
                            Response.grading_lease_expires_at.is_(None),
                            Response.grading_lease_expires_at <= now,
                        ),
                    )
                    .order_by(Response.answered_at)
                    .limit(REQUEUE_BATCH)
                )
            )
            .scalars()
            .all()
        )
        await session.commit()
    for response in rows:
        # The handler grades off the response row alone; only its id travels.
        await ctx["redis"].enqueue_job(JOB_NAME_GRADE_ANSWER_V1, str(response.id))
    return {
        "requeued": len(rows),
        "purged": purged.rowcount,
        "starved": starved.rowcount,
    }
