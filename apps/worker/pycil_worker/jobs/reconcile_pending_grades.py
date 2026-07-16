"""Re-enqueue durable pending grade rows after a lost enqueue or stale lease."""

from datetime import UTC, datetime, timedelta

from pycil.learning.models import GradeStatus, Response
from sqlalchemy import or_, select, update


async def reconcile_pending_grades(ctx: dict) -> dict:
    """Bounded outbox sweep; terminal rows and active leases are never requeued."""
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        purged = await session.execute(
            update(Response)
            .where(
                Response.grade_status == GradeStatus.pending,
                Response.raw_answer.is_not(None),
                Response.answered_at < datetime.now(UTC) - timedelta(hours=24),
            )
            .values(
                grade_status=GradeStatus.expired,
                raw_answer=None,
                grading_lease_owner=None,
                grading_lease_expires_at=None,
            )
        )
        rows = (
            await session.execute(
                select(Response)
                .where(
                    Response.grade_status == GradeStatus.pending,
                    Response.raw_answer.is_not(None),
                    or_(
                        Response.grading_lease_expires_at.is_(None),
                        Response.grading_lease_expires_at <= datetime.now(UTC),
                    ),
                )
                .order_by(Response.answered_at)
                .limit(100)
            )
        ).scalars().all()
        await session.commit()
    for response in rows:
        await ctx["redis"].enqueue_job(
            "grade_answer_v1", str(response.user_id), str(response.id)
        )
    return {"requeued": len(rows), "purged": purged.rowcount}
