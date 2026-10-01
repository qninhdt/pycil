"""Session completion: validation of submitted QuestionResult, atomic state transition,
persistence of Response, ReviewLog, and completion idempotency.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.schemas import CurrentUser
from pycil.library.models import Node
from pycil.platform.errors import ConflictError, NotFoundError
from pycil.study.engine.depth import next_depth_state
from pycil.study.engine.fsrs import GRADE_AGAIN, GRADE_GOOD, initial_state, next_state
from pycil.study.engine.fsrs import mastery as mastery_of
from pycil.study.models import (
    Response,
    ReviewLog,
    SenseStatus,
    SessionSummary,
    StudySession,
    UserSenseStats,
)
from pycil.study.schemas import (
    CompleteSessionRequest,
    LearningPlan,
    SenseMasteryChange,
    SessionResult,
    SessionSummaryStats,
)


async def complete_session(
    session: AsyncSession,
    *,
    user: CurrentUser,
    session_id: str | UUID,
    request: CompleteSessionRequest,
    now: datetime | None = None,
) -> SessionResult:
    """Commit the final session results in a single atomic database transaction."""
    moment = now if now is not None else datetime.now(UTC)
    session_uuid = UUID(str(session_id)) if isinstance(session_id, str) else session_id

    # 1. Lock study_session row FOR UPDATE
    stmt = (
        select(StudySession)
        .where(
            StudySession.id == session_uuid,
            StudySession.user_id == user.id,
        )
        .with_for_update()
    )
    study_session = (await session.execute(stmt)).scalar_one_or_none()
    if study_session is None:
        raise NotFoundError("session_not_found")

    if study_session.node_id is not None:
        node = await session.get(Node, study_session.node_id)
        if node is None:
            raise ConflictError("session_scope_changed")

    # 2. Idempotency: if already completed, return cached SessionResult
    if study_session.status == "completed":
        if study_session.result_summary is not None:
            return SessionResult.model_validate(study_session.result_summary)
        raise ConflictError("session_already_completed")

    # 3. Validate results against the immutable LearningPlan
    plan = LearningPlan.model_validate(study_session.plan)
    plan_by_qid = {item.question_id: item for item in plan.items}

    submitted_qids = [r.question_id for r in request.results]
    if len(submitted_qids) != len(set(submitted_qids)):
        raise ConflictError("duplicate_question_results")

    for r in request.results:
        if r.question_id not in plan_by_qid:
            raise ConflictError("question_not_in_plan")

    if set(submitted_qids) != set(plan_by_qid.keys()):
        raise ConflictError("missing_question_results")

    # 4. Materialize missing learner state for all senses in the LearningPlan
    sense_ids = sorted(list({item.sense_id for item in plan.items}))
    for sense_id in sense_ids:
        insert_stmt = (
            pg_insert(UserSenseStats)
            .values(
                user_id=user.id,
                sense_id=sense_id,
                stability=0.0,
                difficulty=0.0,
                mastery=0,
                interval_days=0.0,
                review_count=0,
                lapse_count=0,
                status=SenseStatus.new,
                depth_level=0,
                depth_streak=0,
                created_at=moment,
                updated_at=moment,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "sense_id"])
        )
        await session.execute(insert_stmt)

    # 5. Batch lock UserSenseStats ordered by sense_id
    lock_stats_stmt = (
        select(UserSenseStats)
        .where(
            UserSenseStats.user_id == user.id,
            UserSenseStats.sense_id.in_(sense_ids),
        )
        .order_by(UserSenseStats.sense_id)
        .with_for_update()
    )
    rows = (await session.execute(lock_stats_stmt)).scalars().all()
    stats_by_sense = {row.sense_id: row for row in rows}

    # 6. Apply learning policy
    results_by_qid = {r.question_id: r for r in request.results}
    changes: list[SenseMasteryChange] = []
    correct_count = 0

    for item in plan.items:
        q_res = results_by_qid[item.question_id]
        verdict = q_res.outcome == "correct"
        if verdict:
            correct_count += 1

        stats = stats_by_sense[item.sense_id]
        stability_before = stats.stability
        mastery_before = stats.mastery
        depth_before = stats.depth_level

        was_new = stats.status == SenseStatus.new or stats.review_count == 0
        if was_new:
            new_state = initial_state(verdict)
            depth_after, streak_after = next_depth_state(0, 0, item.served_level or 1, verdict)
        else:
            new_state = next_state(
                stats.stability,
                stats.difficulty,
                verdict,
                stats.last_review_date,
                moment,
            )
            depth_after, streak_after = next_depth_state(
                stats.depth_level,
                stats.depth_streak,
                item.served_level or 1,
                verdict,
            )

        stats.review_count += 1
        if not verdict:
            stats.lapse_count += 1
        stats.stability = new_state.stability
        stats.difficulty = new_state.difficulty
        stats.mastery = mastery_of(new_state.stability)
        stats.interval_days = new_state.interval_days
        stats.last_review_date = moment
        stats.next_review_date = moment + timedelta(days=new_state.interval_days)
        stats.status = SenseStatus.scheduled
        stats.depth_level = depth_after
        stats.depth_streak = streak_after
        stats.updated_at = moment

        # Persist ReviewLog row
        session.add(
            ReviewLog(
                user_id=user.id,
                sense_id=item.sense_id,
                node_id=study_session.node_id,
                stability_before=stability_before,
                stability_after=stats.stability,
                mastery_before=mastery_before,
                mastery_after=stats.mastery,
                grade=GRADE_GOOD if verdict else GRADE_AGAIN,
                reviewed_at=moment,
            )
        )

        # Persist Response row
        session.add(
            Response(
                user_id=user.id,
                session_id=str(session_uuid),
                sense_id=item.sense_id,
                question_id=item.question_id,
                requested_level=item.requested_level,
                served_level=item.served_level,
                is_correct=verdict,
                grade_status="graded",
                mastery_before=mastery_before,
                mastery_after=stats.mastery,
                depth_before=depth_before,
                depth_after=depth_after,
                answered_at=moment,
                graded_at=moment,
            )
        )

        changes.append(
            SenseMasteryChange(
                sense_id=item.sense_id,
                mastery_before=mastery_before,
                mastery_after=stats.mastery,
                depth_before=depth_before,
                depth_after=depth_after,
            )
        )

    # 7. SessionSummary row for dashboard / history queries
    session.add(
        SessionSummary(
            user_id=user.id,
            session_id=str(session_uuid),
            node_id=study_session.node_id,
            senses_admitted=len(plan.items),
            senses_completed=len(request.results),
            answers_total=len(request.results),
            answers_correct=correct_count,
            rounds_used=1,
            started_at=study_session.created_at,
            completed_at=moment,
        )
    )

    # 8. Complete session result and update StudySession
    session_result = SessionResult(
        session_id=str(session_uuid),
        completed=True,
        summary=SessionSummaryStats(
            questions=len(request.results),
            correct=correct_count,
            incorrect=len(request.results) - correct_count,
            senses_reviewed=len(sense_ids),
        ),
        changes=changes,
    )

    study_session.status = "completed"
    study_session.completed_at = moment
    study_session.result_summary = session_result.model_dump(by_alias=True)

    await session.commit()
    return session_result
