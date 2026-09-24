"""Learning routes: session start, next question (round scheduler + resolver),
answer submission (consume-once bind + two-mode grading).

``/answers`` takes ONLY a question_id + answer — never a client question payload.
The server re-fetches the authoritative question and grades that (answer-key
tamper protection).  All session routes gate the deck via require_node_access.
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import NotFoundError
from pycil.db.redis import get_redis
from pycil.db.session import get_session
from pycil.learning import (
    answering,
    dashboard,
    planning,
    recap,
    response_reads,
)
from pycil.learning import (
    session as study_session,
)
from pycil.learning.delivery import ready_question
from pycil.learning.schemas import (
    AnswerRequest,
    DashboardStatsRead,
    FSRSForecastDay,
    GradeResponse,
    LearningSettingsRead,
    LearningSettingsUpdate,
    NextQuestionBreak,
    NextQuestionExhausted,
    NextQuestionPreparing,
    NextQuestionWaiting,
    ReadyQuestion,
    RecentSessionInfo,
    SessionRead,
    SessionSenseProgressRead,
    SessionStart,
    SessionStateRead,
)
from pycil.ports.lexi import LexiReader
from pycil.ports.lexi_provider import get_lexi_client

router = APIRouter(tags=["learning"])

@router.get("/me/learning-settings", response_model=LearningSettingsRead)
async def get_learning_settings(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> LearningSettingsRead:
    """The caller's effective session shape.

    Resolved through the planner's own reader, so what comes back is what the next
    session will actually use rather than the contents of a row that may not exist.
    A learner who has never set anything gets the policy defaults, not an empty
    object every client would have to interpret.
    """
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
    """Sets the caller's session shape. The upsert lives in ``learning.planning``."""
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
    """The learner's own progress. Read model lives in ``learning.dashboard``."""
    stats = await dashboard.load(session, user.id, datetime.now(UTC))
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


@router.post("/sessions", response_model=SessionRead)
async def start_session(
    body: SessionStart,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> SessionRead:
    """Start a session. Planning and supply warm-up live in ``learning.session``."""
    started = await study_session.start(
        session, get_redis(), user=user, node_id=body.node_id
    )
    return SessionRead(
        session_id=started.session_id,
        node_id=started.node_id,
        admitted_count=started.admitted_count,
        expires_at=started.expires_at.isoformat(),
        first_state="ready" if started.has_work else "exhausted",
    )


@router.get("/sessions/{session_id}", response_model=SessionStateRead)
async def read_session(
    session_id: str,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> SessionStateRead:
    """Read one session. A TRUE read — it advances nothing and reserves nothing.

    Unlike ``/next``, which is a mutation dressed as a GET (it advances rounds,
    reserves deliveries and extends the exclusion set), this endpoint is safe to
    poll, retry and prefetch.

    Live sessions are served from Redis. Once a session completes, ``end_session``
    has deleted that namespace, so the durable recap answers instead. 404 only when
    neither exists.
    """
    live = await study_session.read_live(
        session, get_redis(), session_id, user_id=user.id
    )
    if live is not None:
        return SessionStateRead(
            session_id=session_id,
            status="live",
            node_id=live.meta.node_id,
            round_index=live.meta.round_index,
            round_count=live.meta.round_count,
            max_per_round=live.meta.max_per_round,
            expires_at=live.meta.expires_at.isoformat(),
            senses=[
                SessionSenseProgressRead(
                    sense_id=item.sense_id,
                    purpose=item.purpose,
                    graded=item.graded,
                    exposed=item.exposed,
                    reask_pending=item.reask_pending,
                    terminal=item.terminal,
                    terminal_reason=item.terminal_reason,
                )
                for item in live.senses
            ],
            senses_admitted=live.senses_admitted,
            senses_completed=live.senses_completed,
            answers_total=live.answers_total,
            answers_correct=live.answers_correct,
            rounds_used=live.meta.round_index + 1,
        )

    summary = await recap.load(session, user.id, session_id)
    if summary is None:
        raise NotFoundError("session_not_found")
    return SessionStateRead(
        session_id=session_id,
        status="completed",
        node_id=summary.node_id,
        senses_admitted=summary.senses_admitted,
        senses_completed=summary.senses_completed,
        answers_total=summary.answers_total,
        answers_correct=summary.answers_correct,
        rounds_used=summary.rounds_used,
        completed_at=summary.completed_at.isoformat() if summary.completed_at else None,
    )


@router.get(
    "/sessions/{session_id}/next",
    response_model=(
        ReadyQuestion
        | NextQuestionBreak
        | NextQuestionPreparing
        | NextQuestionWaiting
        | NextQuestionExhausted
    ),
)
async def next_question(
    session_id: str,
    user: Annotated[CurrentUser, Depends(current_user)],
    client: LexiReader = Depends(get_lexi_client),
    session: AsyncSession = Depends(get_session),
):
    """Advance the session by at most one delivery.

    A mutation modelled as a GET: it advances rounds, reserves deliveries and extends
    the exclusion set. The scheduling itself lives in ``learning.session``; this
    only maps its outcome onto the wire.
    """
    redis = get_redis()
    meta = await study_session.authorize(session, redis, session_id, user)
    outcome = await study_session.next_question(
        session, redis, client, session_id=session_id, user=user, meta=meta
    )
    if isinstance(outcome, study_session.Delivered):
        return ready_question(outcome.resolved)
    if isinstance(outcome, study_session.RoundBreak):
        return NextQuestionBreak(round_index=outcome.round_index)
    if outcome.reason == "exhausted":
        return NextQuestionExhausted()
    if outcome.reason == "waiting":
        return NextQuestionWaiting()
    return NextQuestionPreparing(task_id=outcome.supply_task_id)


@router.post("/answers", response_model=GradeResponse, response_model_exclude_none=True)
async def submit_answer(
    body: AnswerRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
) -> GradeResponse:
    """Grade one answer.

    Takes ONLY a question id and an answer — never a client question payload. The
    server re-fetches the authoritative question and grades that, which is what makes
    answer-key tampering impossible. Binding, evaluation and the compensation matrix
    live in ``learning.answering``.
    """
    redis = get_redis()
    # Called for its guards, not its value: 404 unless the session is the caller's,
    # 409 if a structural mutation moved the scope out from under it.
    await study_session.authorize(session, redis, body.session_id, user)
    outcome = await answering.submit(
        session,
        redis,
        client,
        user=user,
        session_id=body.session_id,
        question_id=body.question_id,
        answer=body.answer,
        now=datetime.now(UTC),
    )
    if isinstance(outcome, answering.UngradedReask):
        return GradeResponse(
            response_id=None,
            grade_status="ungraded",
            sense_id=outcome.sense_id,
            render_format=outcome.render_format,
            is_correct=outcome.is_correct,
            grade_score=outcome.grade_score,
            grade_feedback=outcome.grade_feedback,
            reveal=outcome.reveal,
        )
    return GradeResponse(
        response_id=outcome.response_id,
        grade_status="graded",
        sense_id=outcome.sense_id,
        render_format=outcome.render_format,
        is_correct=outcome.is_correct,
        grade_score=outcome.grade_score,
        grade_feedback=outcome.grade_feedback,
        reveal=outcome.reveal,
        mastery_before=outcome.mastery_before,
        mastery_after=outcome.mastery_after,
        depth_before=outcome.depth_before,
        depth_after=outcome.depth_after,
        depth_stage_name=outcome.depth_stage_name,
    )


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
    return await response_reads.get_response(session, user.id, response_id)
