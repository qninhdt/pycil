"""Learning routes: session start, next question (round scheduler + resolver),
answer submission (consume-once bind + two-mode grading).

``/answers`` takes ONLY a question_id + answer — never a client question payload.
The server re-fetches the authoritative question and grades that (answer-key
tamper protection).  All session routes gate the deck via require_node_access.
"""

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ConflictError, NotFoundError, ServiceUnavailableError
from pycil.content.deps import get_lexi_client
from pycil.content.lexi_port import LexiReader
from pycil.db.redis import get_arq_pool, get_redis
from pycil.db.session import get_session
from pycil.hierarchy.access import require_node_access
from pycil.hierarchy.models import Node, NodeType
from pycil.learning import (
    grading,
    planning,
    resolver,
    round_scheduler,
    service,
    session_recap,
    session_store,
)
from pycil.learning.models import (
    Response,
    ReviewLog,
    UserLearningSettings,
    UserSenseStats,
)
from pycil.learning.question_delivery import (
    presentation_payload,
    render_format,
)
from pycil.learning.resolver import ResolvedQuestion
from pycil.learning.schemas import (
    AnswerRequest,
    DashboardStatsRead,
    FlashcardReady,
    FreeTextReady,
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
    SingleChoiceReady,
    TextSpanReady,
)
from pycil.tasks import service as task_service
from pycil.tasks.work_keys import grading_work_key

router = APIRouter(tags=["learning"])

_READY_CLASSES = {
    "flashcard": FlashcardReady,
    "single_choice": SingleChoiceReady,
    "text_span": TextSpanReady,
    "free_text": FreeTextReady,
}


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
    """Sets the caller's session shape, creating the row on first write.

    A real upsert rather than a read-then-branch. The row is absent until someone
    saves, and a SELECT finding nothing locks nothing — so two tabs saving at once
    would both take the insert branch and the second would fail on the primary key.
    ``ON CONFLICT`` makes the first write idempotent for the same reason the session
    recap needs it.

    A live session is unaffected. It carries the plan it was created with, so a
    change here applies from the next session, which is what the form says.
    """
    now = datetime.now(UTC)
    statement = pg_insert(UserLearningSettings).values(
        user_id=user.id,
        target_words_per_session=body.target_words_per_session,
        max_questions_per_round=body.max_questions_per_round,
        updated_at=now,
    )
    await session.execute(
        statement.on_conflict_do_update(
            # Named as a string rather than as the model attribute: SQLModel's
            # annotation resolves to the Python type, not to a Column, so passing the
            # attribute here does not describe an index target.
            index_elements=["user_id"],
            set_={
                "target_words_per_session": statement.excluded.target_words_per_session,
                "max_questions_per_round": statement.excluded.max_questions_per_round,
                "updated_at": statement.excluded.updated_at,
            },
        )
    )
    await session.commit()

    return LearningSettingsRead(
        target_words_per_session=body.target_words_per_session,
        max_questions_per_round=body.max_questions_per_round,
    )


@router.get("/learning/dashboard", response_model=DashboardStatsRead)
async def get_dashboard_stats(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> DashboardStatsRead:
    now = datetime.now(UTC)

    learned_stmt = select(func.count(UserSenseStats.sense_id)).where(
        UserSenseStats.user_id == user.id,
        (UserSenseStats.mastery > 0) | (UserSenseStats.review_count > 0),
    )
    total_learned = (await session.execute(learned_stmt)).scalar() or 0

    due_stmt = select(func.count(UserSenseStats.sense_id)).where(
        UserSenseStats.user_id == user.id,
        UserSenseStats.next_review_date <= now,
    )
    due_today = (await session.execute(due_stmt)).scalar() or 0

    mastery_stmt = select(func.avg(UserSenseStats.mastery)).where(
        UserSenseStats.user_id == user.id,
        (UserSenseStats.mastery > 0) | (UserSenseStats.review_count > 0),
    )
    avg_mastery_res = (await session.execute(mastery_stmt)).scalar()
    avg_mastery = float(avg_mastery_res) if avg_mastery_res is not None else 0.0

    forecast: list[FSRSForecastDay] = []
    stats_rows = (
        await session.scalars(
            select(UserSenseStats).where(
                UserSenseStats.user_id == user.id,
                UserSenseStats.next_review_date.is_not(None),
            )
        )
    ).all()

    today_date = now.date()
    counts = {today_date + timedelta(days=i): 0 for i in range(7)}
    for s in stats_rows:
        if s.next_review_date:
            d = s.next_review_date.date()
            if d <= today_date:
                counts[today_date] += 1
            elif d in counts:
                counts[d] += 1
    for i in range(7):
        d = today_date + timedelta(days=i)
        forecast.append(FSRSForecastDay(date=d.isoformat(), due_count=counts[d]))

    recent_log_stmt = (
        select(ReviewLog)
        .where(ReviewLog.user_id == user.id, ReviewLog.node_id.is_not(None))
        .order_by(ReviewLog.reviewed_at.desc())
        .limit(1)
    )
    recent_log = (await session.execute(recent_log_stmt)).scalar_one_or_none()
    recent_session_info = None
    if recent_log and recent_log.node_id:
        node = await session.get(Node, recent_log.node_id)
        if node:
            recent_session_info = RecentSessionInfo(
                node_id=node.id, deck_title=node.name, remaining_count=due_today
            )
    if recent_session_info is None:
        first_deck = (
            await session.scalars(
                select(Node).where(Node.author_id == user.id, Node.type == NodeType.DECK).limit(1)
            )
        ).first()
        if first_deck:
            recent_session_info = RecentSessionInfo(
                node_id=first_deck.id, deck_title=first_deck.name, remaining_count=due_today
            )

    return DashboardStatsRead(
        total_learned_words=total_learned,
        due_today_count=due_today,
        mastery_percentage=round(avg_mastery, 1),
        fsrs_forecast=forecast,
        recent_session=recent_session_info,
    )


@router.post("/sessions", response_model=SessionRead)
async def start_session(
    body: SessionStart,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> SessionRead:
    now = datetime.now(UTC)
    session_id = uuid.uuid4().hex
    rng = random.Random(session_id)
    # A structural mutation can change the canonical resolver while this request
    # runs.  Retry once so the plan carries the generation it was resolved from.
    # Session shape is the learner's, not the node's, so it is resolved once here
    # rather than per node kind. A folder session and a deck session now get the
    # same shape, which is what the learner configured.
    settings = await planning.settings_for_user(session, user.id)
    plan = None
    for _ in range(2):
        node = await require_node_access(session, body.node_id, user, write=False)
        generation = node.structural_generation
        plan = await planning.plan_session(session, user.id, body.node_id, now, settings, rng)
        node = await require_node_access(session, body.node_id, user, write=False)
        if node.structural_generation == generation:
            break
    else:
        raise ConflictError("session_scope_changed")

    redis = get_redis()
    meta = await session_store.create(
        redis,
        session_id,
        owner_id=user.id,
        node_id=body.node_id,
        scope_generation=node.structural_generation,
        target_words=settings.target_words_per_session,
        max_per_round=settings.max_questions_per_round,
        admitted=plan.admitted,
    )
    # Supply warm-up is retried with a session-scoped cooldown and hard budget.
    if plan.demands and await session_store.take_generation_slot(redis, user.id):
        prepare_state = await session_store.claim_prepare_attempt(redis, session_id)
        if prepare_state == "claimed":
            try:
                pool = await get_arq_pool()
                await pool.enqueue_job(
                    "prepare_questions",
                    str(user.id),
                    [
                        (int(d.sense_id), d.difficulty_level, d.expected_count)
                        for d in plan.demands
                    ],
                )
            except Exception:
                # The consumed attempt enters cooldown; /next retries after it.
                pass

    return SessionRead(
        session_id=session_id,
        node_id=body.node_id,
        admitted_count=len(plan.admitted),
        expires_at=meta.expires_at.isoformat(),
        first_state="ready" if plan.admitted else "exhausted",
    )


def _build_ready(resolved: ResolvedQuestion) -> ReadyQuestion:
    question = resolved.question
    format_name = render_format(question)
    ready_cls = _READY_CLASSES.get(format_name)
    if ready_cls is None:
        raise ServiceUnavailableError("lexi_render_format_unsupported")
    if question.sense_id is None:
        raise ServiceUnavailableError("lexi_question_presentation_invalid")
    try:
        sense_id = int(question.sense_id)
        question_id = (
            None if question.interaction == "exposure" else int(question.question_id)
        )
    except (TypeError, ValueError) as err:
        raise ServiceUnavailableError("lexi_question_presentation_invalid") from err
    return ready_cls(
        question_id=question_id,
        sense_id=sense_id,
        interaction_mode=question.interaction,
        requested_level=resolved.requested_level,
        served_level=resolved.served_level,
        is_fallback=resolved.is_fallback,
        payload=presentation_payload(question),
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
    redis = get_redis()
    meta = await session_store.get_meta(redis, session_id)
    if meta is not None:
        if meta.owner_id != user.id:
            # Same 404 as an unknown id: never confirm that someone else's session
            # exists.
            raise NotFoundError("session_not_found")
        admitted = await session_store.get_admitted(redis, session_id)
        senses: list[SessionSenseProgressRead] = []
        completed = 0
        exhausted = 0
        for sense_id, purpose in sorted(admitted.items()):
            progress = await session_store.get_progress(redis, session_id, sense_id)
            if progress is None:
                continue
            if progress.terminal_reason == "retries_exhausted":
                exhausted += 1
            elif progress.terminal:
                completed += 1
            senses.append(
                SessionSenseProgressRead(
                    sense_id=sense_id,
                    purpose=purpose,
                    passed=progress.passed,
                    required=len(progress.requested_levels),
                    score=progress.score,
                    exposed=progress.exposed,
                    awaiting_grade=progress.awaiting_grade,
                    terminal=progress.terminal,
                    terminal_reason=progress.terminal_reason,
                )
            )
        answers_total, answers_correct = await session_recap.answer_counts(
            session, user.id, session_id
        )
        return SessionStateRead(
            session_id=session_id,
            status="live",
            node_id=meta.node_id,
            round_index=meta.round_index,
            round_count=meta.round_count,
            max_per_round=meta.max_per_round,
            expires_at=meta.expires_at.isoformat(),
            senses=senses,
            senses_admitted=len(admitted),
            senses_completed=completed,
            senses_exhausted=exhausted,
            answers_total=answers_total,
            answers_correct=answers_correct,
            rounds_used=meta.round_index + 1,
        )

    summary = await session_recap.load(session, user.id, session_id)
    if summary is None:
        raise NotFoundError("session_not_found")
    return SessionStateRead(
        session_id=session_id,
        status="completed",
        node_id=summary.node_id,
        senses_admitted=summary.senses_admitted,
        senses_completed=summary.senses_completed,
        senses_exhausted=summary.senses_exhausted,
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
    redis = get_redis()
    meta = await session_store.get_meta(redis, session_id)
    if meta is None or meta.owner_id != user.id:
        raise NotFoundError("session_not_found")
    node = await require_node_access(session, meta.node_id, user, write=False)
    if node.structural_generation != meta.scope_generation:
        raise ConflictError("session_scope_changed")

    cur = await session_store.current_round(redis, session_id)
    # Round full -> offer a break; the next poll advances into a fresh round.
    if cur >= 1 and meta.round_count >= meta.max_per_round:
        await session_store.advance_round(redis, session_id, expected_round=cur)
        return NextQuestionBreak(round_index=cur + 1)
    if cur == 0:
        cur = await session_store.advance_round(redis, session_id, expected_round=0)

    candidates = await round_scheduler.round_candidates(redis, session_id, cur)
    unresolved_demands: list[tuple[int, int, int]] = []
    rng = random.Random(f"{session_id}:{cur}")
    for requirement in candidates:
        sense_id = requirement.sense_id
        if requirement.kind == "exposure":
            try:
                resolved = await resolver.resolve_exposure(client, sense_id)
            except LookupError:
                continue  # F14: missing/stale sense -> defer, do not 500
            if not await session_store.reserve_round_delivery(
                redis, session_id, sense_id, cur, question_id=None
            ):
                continue
            return _build_ready(resolved)

        excluded = await session_store.excluded_ids(redis, session_id, sense_id)
        resolved = await resolver.resolve(
            client, sense_id, requirement.requested_level, excluded, rng
        )
        if resolved is None:
            unresolved_demands.append((sense_id, requirement.requested_level, 1))
            continue  # defer: supply not warm -> try next candidate
        try:
            qid = int(resolved.question.question_id)
        except (TypeError, ValueError):
            continue  # assessment ids must remain integer-compatible on the REST wire
        if not await session_store.reserve_round_delivery(
            redis, session_id, sense_id, cur, question_id=qid
        ):
            continue
        return _build_ready(resolved)

    # Nothing delivered this round. Retry unresolved supply with cooldown + budget.
    if unresolved_demands:
        if not await session_store.take_generation_slot(redis, user.id):
            return NextQuestionPreparing()
        prepare_state = await session_store.claim_prepare_attempt(redis, session_id)
        if prepare_state == "claimed":
            try:
                pool = await get_arq_pool()
                await pool.enqueue_job(
                    "prepare_questions", str(user.id), unresolved_demands
                )
            except Exception:
                pass
            return NextQuestionPreparing()
        if prepare_state == "waiting":
            return NextQuestionPreparing()
        raise ServiceUnavailableError("question_preparation_exhausted")
    if candidates:
        # A concurrent request reserved the eligible candidate first.
        return NextQuestionPreparing()
    if await round_scheduler.has_open_work(redis, session_id):
        # Remaining work waits for a later round (retries / used-this-round).
        await session_store.advance_round(redis, session_id, expected_round=cur)
        return NextQuestionBreak(round_index=cur + 1)
    if await round_scheduler.session_complete(session, redis, session_id):
        # The recap must be written while the Redis state still exists — end_session
        # deletes the namespace on the next line.
        await session_recap.persist(
            session, redis, session_id, user_id=user.id, node_id=meta.node_id
        )
        await session_store.end_session(redis, session_id)
        return NextQuestionExhausted()
    return NextQuestionWaiting()


@router.post("/answers", response_model=GradeResponse)
async def submit_answer(
    body: AnswerRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
) -> GradeResponse:
    now = datetime.now(UTC)
    redis = get_redis()
    meta = await session_store.get_meta(redis, body.session_id)
    if meta is None or meta.owner_id != user.id:
        raise NotFoundError("session_not_found")
    node = await require_node_access(session, meta.node_id, user, write=False)
    if node.structural_generation != meta.scope_generation:
        raise ConflictError("session_scope_changed")

    question = await client.get_question(body.question_id)
    sense_id: int | None = None
    if question is not None and question.sense_id is not None:
        try:
            sense_id = int(question.sense_id)
        except (TypeError, ValueError):
            sense_id = None
    if sense_id is None:
        # Purged/regenerated question (F14) — reject gracefully, not a 500. But the
        # sense is still BOUND to this question id, and nobody can ever submit it
        # again now that it is gone, so the checkpoint has to be reopened here or
        # that sense is undeliverable for the rest of the session.
        await session_store.reopen_bound_delivery(redis, body.session_id, body.question_id)
        raise ConflictError("question_not_available")
    if question.interaction != "assessment":
        await session_store.reopen_bound_delivery(redis, body.session_id, body.question_id)
        raise ConflictError("question_not_assessable")

    # Consume-once bind (F5): the submitted question must be the sense's currently
    # delivered checkpoint; a replayed/self-selected id is rejected.
    if not await session_store.consume_delivered(
        redis, body.session_id, sense_id, body.question_id
    ):
        raise ConflictError("question_not_issued_for_session")

    committed = False
    try:
        progress = await session_store.get_progress(redis, body.session_id, sense_id)
        if progress is None:
            raise ConflictError("question_not_issued_for_session")
        if progress.open_checkpoint is not None:
            requested_level = progress.open_requested_level
        elif progress.passed < len(progress.requested_levels):
            requested_level = progress.requested_levels[progress.passed]
        else:
            requested_level = question.difficulty_level
        served_level = question.difficulty_level
        format_name = render_format(question)

        evaluation = await client.evaluate_answer(
            body.question_id,
            grading.answer_submission(question, body.answer),
        )
        if evaluation is None:
            raise ConflictError("question_not_assessable")

        if evaluation.status == "graded":
            # Rule type: apply the consequence synchronously and return the verdict.
            response = Response(
                user_id=user.id,
                session_id=body.session_id,
                sense_id=sense_id,
                question_id=body.question_id,
                requested_level=requested_level,
                served_level=served_level,
                raw_answer=None,
                idempotency_key=f"{body.session_id}:{body.question_id}",
            )
            session.add(response)
            await session.flush()
            outcome = await service.apply_checkpoint_result(
                session,
                redis,
                response=response,
                verdict=bool(evaluation.correct),
                score=evaluation.score,
                feedback=evaluation.feedback,
                now=now,
                render_format=format_name,
                reveal=evaluation.reveal,
            )
            # The verdict is durably applied; a later failure must NOT re-arm the
            # consume-once bind (that would let a retry double-insert the row).
            committed = True
            return GradeResponse(
                response_id=outcome.response_id,
                grade_status="graded",
                sense_id=sense_id,
                render_format=format_name,
                is_correct=outcome.is_correct,
                grade_score=outcome.grade_score,
                grade_feedback=outcome.grade_feedback,
                reveal=outcome.reveal,
                mastery_before=outcome.mastery_before,
                mastery_after=outcome.mastery_after,
            )

        # llm type: defer to the worker + SSE settle.
        if not await session_store.take_grading_slot(redis, user.id):
            raise ConflictError("answer_grading_quota_exceeded")
        response = await service.create_pending_response(
            session,
            user_id=user.id,
            session_id=body.session_id,
            sense_id=sense_id,
            question_id=body.question_id,
            raw_answer=body.answer,
            idempotency_key=f"{body.session_id}:{body.question_id}",
            requested_level=requested_level,
            served_level=served_level,
            render_format=format_name,
        )
        # The pending row is durable (reconcile owns its settle); do not re-arm the
        # consume-once bind on a later failure in this request.
        committed = True
        await session_store.set_awaiting_grade(redis, body.session_id, sense_id, True)
        submission = await task_service.submit_or_join(
            session,
            kind="grading",
            server_work_key=grading_work_key(str(response.id)),
            requester_id=user.id,
            command_kind="grading.submit",
            command_id=str(response.id),
            provenance="response-owner",
            dispatch={"owner_id": str(user.id), "response_id": str(response.id)},
        )
        if submission.task_created:
            try:
                pool = await get_arq_pool()
                await pool.enqueue_job(
                    "grade_answer_task", str(submission.task.id), str(user.id), str(response.id)
                )
            except Exception:  # durable worker reconciliation retries the enqueue
                pass
        return GradeResponse(
            response_id=response.id,
            grade_status="pending",
            sense_id=sense_id,
            render_format=format_name,
            task_id=submission.task.id,
        )
    except Exception:
        # Release the consume-once claim so the learner can retry — but only if no
        # durable response row was written yet (else a retry would double-insert).
        if not committed:
            await session_store.restore_delivered(
                redis, body.session_id, sense_id, body.question_id
            )
        raise
