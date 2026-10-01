"""Study API router for learning sessions, settings, dashboard, and grading.

Supports the three primary session operations:
1. create_session (POST /study/sessions or /sessions) -> LearningPlan + questions
2. grade_answer (POST /study/sessions/{session_id}/grade) -> semantic grading
3. complete_session (POST /study/sessions/{session_id}/complete) -> QuestionResult[]
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.auth import current_user
from pycil.account.schemas import CurrentUser
from pycil.lexicon.contracts import LexiReader
from pycil.lexicon.provider import get_lexi_client
from pycil.library.access import require_node_access
from pycil.platform.database import get_session
from pycil.platform.errors import NotFoundError
from pycil.study import completion, grading, planning
from pycil.study.models import Response, SessionSummary, StudySession
from pycil.study.schemas import (
    CompleteSessionRequest,
    DashboardStatsRead,
    FSRSForecastDay,
    GradeAnswerRequest,
    GradeAnswerResponse,
    GradeResponse,
    LearningPlan,
    LearningSettingsRead,
    LearningSettingsUpdate,
    RecentSessionInfo,
    SessionCreateResponse,
    SessionResult,
    SessionStart,
    SessionStateRead,
)

router = APIRouter(tags=["study"])


@router.get("/me/learning-settings", response_model=LearningSettingsRead)
async def get_learning_settings(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> LearningSettingsRead:
    """The caller's effective session shape."""
    effective = await planning.settings_for_user(session, user.id)
    return LearningSettingsRead(
        target_words_per_session=effective.target_words_per_session,
        max_questions_per_round=effective.max_questions_per_round,
    )


@router.patch("/me/learning-settings", response_model=LearningSettingsRead)
async def update_learning_settings(
    body: LearningSettingsUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> LearningSettingsRead:
    """Sets the caller's session shape."""
    saved = await planning.save_settings(
        session,
        user.id,
        target_words_per_session=body.target_words_per_session,
        max_questions_per_round=body.max_questions_per_round,
    )
    return LearningSettingsRead(
        target_words_per_session=saved.target_words_per_session,
        max_questions_per_round=saved.max_questions_per_round,
    )


@router.get("/learning/dashboard", response_model=DashboardStatsRead)
async def get_dashboard_stats(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> DashboardStatsRead:
    """The learner's own progress."""
    stats = await planning.load_dashboard(session, user.id, datetime.now(UTC))
    return DashboardStatsRead(
        total_learned_words=stats.total_learned_words,
        due_today_count=stats.due_today_count,
        mastery_percentage=stats.mastery_percentage,
        fsrs_forecast=[
            FSRSForecastDay(date=day.day.isoformat(), due_count=day.due_count)
            for day in stats.forecast
        ],
        recent_session=(
            None
            if stats.resume is None
            else RecentSessionInfo(
                node_id=stats.resume.node_id,
                deck_title=stats.resume.deck_title,
                remaining_count=stats.resume.remaining_count,
            )
        ),
    )


@router.post("/study/sessions", response_model=SessionCreateResponse)
@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session(
    body: SessionStart,
    background_tasks: BackgroundTasks,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
) -> SessionCreateResponse:
    """Create a new study session with an immutable LearningPlan and all questions upfront."""
    await require_node_access(session, body.node_id, user)
    now = datetime.now(UTC)
    settings = await planning.settings_for_user(session, user.id)

    learning_plan, questions = await planning.create_session_learning_plan(
        session,
        client,
        user.id,
        body.node_id,
        now,
        settings,
    )

    study_session = StudySession(
        user_id=user.id,
        node_id=body.node_id,
        status="active",
        created_at=now,
        expires_at=now + timedelta(days=1),
        plan=learning_plan.model_dump(by_alias=True),
    )
    session.add(study_session)
    await session.commit()
    await session.refresh(study_session)

    return SessionCreateResponse(
        session_id=str(study_session.id),
        node_id=body.node_id,
        admitted_count=len(learning_plan.items),
        expires_at=study_session.expires_at.isoformat() if study_session.expires_at else "",
        first_state="ready" if learning_plan.items else "exhausted",
        plan=learning_plan,
        questions=questions,
    )


@router.post(
    "/study/sessions/{session_id}/grade",
    response_model=GradeAnswerResponse,
    response_model_exclude_none=True,
)
@router.post(
    "/sessions/{session_id}/grade",
    response_model=GradeAnswerResponse,
    response_model_exclude_none=True,
)
async def grade_answer(
    session_id: str,
    body: GradeAnswerRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
) -> GradeAnswerResponse:
    """Stateless server-side grading for semantic / open-ended questions."""
    return await grading.grade_server_question(
        session,
        client,
        user=user,
        session_id=session_id,
        question_id=body.question_id,
        answer=body.answer,
    )


@router.post(
    "/study/sessions/{session_id}/complete",
    response_model=SessionResult,
)
@router.post(
    "/sessions/{session_id}/complete",
    response_model=SessionResult,
)
async def complete_session_endpoint(
    session_id: str,
    body: CompleteSessionRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> SessionResult:
    """Complete a learning session and commit all QuestionResults atomically."""
    return await completion.complete_session(
        session,
        user=user,
        session_id=session_id,
        request=body,
    )


@router.get("/study/sessions/{session_id}", response_model=SessionStateRead)
@router.get("/sessions/{session_id}", response_model=SessionStateRead)
async def read_session(
    session_id: str,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> SessionStateRead:
    """Read session state: active plan or completed summary."""
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        session_uuid = None

    if session_uuid is not None:
        study_session = await session.get(StudySession, session_uuid)
        if study_session is not None and study_session.user_id == user.id:
            if study_session.status == "completed":
                summary = (
                    study_session.result_summary.get("summary", {})
                    if study_session.result_summary
                    else {}
                )
                return SessionStateRead(
                    session_id=str(study_session.id),
                    status="completed",
                    node_id=study_session.node_id,
                    senses_admitted=summary.get("sensesReviewed", 0),
                    senses_completed=summary.get("questions", 0),
                    answers_total=summary.get("questions", 0),
                    answers_correct=summary.get("correct", 0),
                    rounds_used=1,
                    completed_at=(
                        study_session.completed_at.isoformat()
                        if study_session.completed_at
                        else None
                    ),
                )
            plan = LearningPlan.model_validate(study_session.plan)
            return SessionStateRead(
                session_id=str(study_session.id),
                status="live",
                node_id=study_session.node_id,
                round_index=0,
                round_count=1,
                max_per_round=len(plan.items),
                expires_at=(
                    study_session.expires_at.isoformat() if study_session.expires_at else None
                ),
                senses_admitted=len(plan.items),
                senses_completed=0,
                answers_total=0,
                answers_correct=0,
                rounds_used=0,
            )

    # Fallback to legacy SessionSummary
    summary_stmt = select(SessionSummary).where(
        SessionSummary.session_id == session_id,
        SessionSummary.user_id == user.id,
    )
    summary_row = (await session.execute(summary_stmt)).scalar_one_or_none()
    if summary_row is not None:
        return SessionStateRead(
            session_id=session_id,
            status="completed",
            node_id=summary_row.node_id,
            senses_admitted=summary_row.senses_admitted,
            senses_completed=summary_row.senses_completed,
            answers_total=summary_row.answers_total,
            answers_correct=summary_row.answers_correct,
            rounds_used=summary_row.rounds_used,
            completed_at=(
                summary_row.completed_at.isoformat() if summary_row.completed_at else None
            ),
        )

    raise NotFoundError("session_not_found")


@router.get(
    "/responses/{response_id}",
    response_model=GradeResponse,
    response_model_exclude_none=True,
)
async def get_response(
    response_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> GradeResponse:
    """Return the durable answer projection for the authenticated owner."""
    response = await session.scalar(
        select(Response).where(
            Response.id == response_id,
            Response.user_id == user.id,
        )
    )
    if response is None:
        raise NotFoundError("response_not_found")

    return GradeResponse(
        response_id=response.id,
        grade_status=str(response.grade_status),
        sense_id=response.sense_id,
        render_format=response.render_format or "free_text",
        is_correct=response.is_correct,
        grade_score=response.grade_score,
        grade_feedback=response.grade_feedback,
        reveal=response.reveal,
        mastery_before=response.mastery_before,
        mastery_after=response.mastery_after,
        depth_before=response.depth_before,
        depth_after=response.depth_after,
    )
