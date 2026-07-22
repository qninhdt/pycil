"""Learning routes: session start, next question, answer submission.

/answers takes ONLY a question_id + answer — never a client question payload. The
server re-fetches the authoritative question and grades that (answer-key tamper
protection). All session routes gate the deck via require_node_access.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ConflictError, NotFoundError
from pycil.content.deps import get_lexi_client
from pycil.content.lexi_port import LexiReader
from pycil.db.redis import get_arq_pool, get_redis
from pycil.db.session import get_session
from pycil.hierarchy.access import require_node_access
from pycil.hierarchy.models import DeckAttributes, Node, NodeType
from pycil.learning import question_delivery, service, session_queue, session_store
from pycil.learning.models import ReviewLog, UserSenseStats
from pycil.learning.router_question import choose_format
from pycil.learning.schemas import (
    AnswerRequest,
    DashboardStatsRead,
    FSRSForecastDay,
    GradeResponse,
    NextQuestionExhausted,
    NextQuestionPending,
    ReadyQuestion,
    RecentSessionInfo,
    SessionRead,
    SessionStart,
)
from pycil.tasks import service as task_service
from pycil.tasks.models import AsyncTaskStatus
from pycil.tasks.work_keys import grading_work_key, question_pool_work_key

router = APIRouter(tags=["learning"])
_QUESTION_GENERATOR_REVISION = "v1"
_QUESTION_POOL_GENERATION = 0


@router.get("/learning/dashboard", response_model=DashboardStatsRead)
async def get_dashboard_stats(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> DashboardStatsRead:
    now = datetime.now(UTC)

    # 1. Total learned words (mastery > 0 or review_count > 0)
    learned_stmt = select(func.count(UserSenseStats.sense_id)).where(
        UserSenseStats.user_id == user.id,
        (UserSenseStats.mastery > 0) | (UserSenseStats.review_count > 0),
    )
    total_learned = (await session.execute(learned_stmt)).scalar() or 0

    # 2. Due today count (next_review_date <= now)
    due_stmt = select(func.count(UserSenseStats.sense_id)).where(
        UserSenseStats.user_id == user.id,
        UserSenseStats.next_review_date <= now,
    )
    due_today = (await session.execute(due_stmt)).scalar() or 0

    # 3. Average mastery percentage
    mastery_stmt = select(func.avg(UserSenseStats.mastery)).where(
        UserSenseStats.user_id == user.id,
        (UserSenseStats.mastery > 0) | (UserSenseStats.review_count > 0),
    )
    avg_mastery_res = (await session.execute(mastery_stmt)).scalar()
    avg_mastery = float(avg_mastery_res) if avg_mastery_res is not None else 0.0

    # 4. FSRS 7-Day Forecast (Today + next 6 days)
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

    # 5. Recent Session Target
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

def _seen_key(session_id: str) -> str:
    return f"session:seen:{session_id}"


@router.post("/sessions", response_model=SessionRead)
async def start_session(
    body: SessionStart,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> SessionRead:
    now = datetime.now(UTC)
    # A structural mutation can change the canonical resolver while this request
    # runs.  Retry once so the persisted queue always carries the generation it
    # was resolved from rather than labelling an old queue with a new generation.
    for _ in range(2):
        node = await require_node_access(session, body.node_id, user, write=False)
        generation = node.structural_generation
        queue_kwargs = {}
        if node.type == NodeType.DECK:
            attributes = await session.get(DeckAttributes, node.id)
            new_per_batch, review_per_batch = session_queue.ratio_from_settings(
                attributes.settings if attributes else None
            )
            queue_kwargs = {
                "new_per_batch": new_per_batch,
                "review_per_batch": review_per_batch,
            }
        queue = await session_queue.build_queue(
            session, user.id, body.node_id, now, **queue_kwargs
        )
        node = await require_node_access(session, body.node_id, user, write=False)
        if node.structural_generation == generation:
            break
    else:
        raise ConflictError("session_scope_changed")
    session_id = uuid.uuid4().hex
    redis = get_redis()
    state = await session_store.create(
        redis,
        session_id,
        owner_id=user.id,
        node_id=body.node_id,
        scope_generation=node.structural_generation,
        queue=[session_store.QueuedSense(item.sense_id, item.mastery) for item in queue],
    )
    return SessionRead(
        session_id=session_id,
        node_id=body.node_id,
        queue_size=len(queue),
        expires_at=state.expires_at.isoformat(),
        first_state="pending" if queue else "exhausted",
    )


@router.get(
    "/sessions/{session_id}/next",
    response_model=ReadyQuestion | NextQuestionPending | NextQuestionExhausted,
)
async def next_question(
    session_id: str,
    user: Annotated[CurrentUser, Depends(current_user)],
    client: LexiReader = Depends(get_lexi_client),
    session: AsyncSession = Depends(get_session),
):
    redis = get_redis()
    state = await session_store.get(redis, session_id)
    if state is None or state.owner_id != user.id:
        raise NotFoundError("session_not_found")
    node = await require_node_access(session, state.node_id, user, write=False)
    if node.structural_generation != state.scope_generation:
        raise ConflictError("session_scope_changed")
    if state.issue and state.issue["state"] == "ready":
        return state.issue
    if state.issue and state.issue["state"] == "answering":
        raise ConflictError("question_answer_in_progress")
    if state.issue and state.issue["state"] == "generation_pending":
        delivery_id = state.issue.get("delivery_id")
        if delivery_id:
            delivery = await task_service.get_question_delivery(
                session, uuid.UUID(delivery_id), session_id=session_id, owner_id=user.id
            )
            if delivery and delivery.snapshot:
                question = await client.get_question(delivery.snapshot["questionId"])
                if question is None:
                    raise ConflictError("question_delivery_mismatch")
                issue = {
                    "state": "ready",
                    **question_delivery.ready_payload(question, delivery.question_format),
                }
                if not await session_store.replace_issue(redis, session_id, issue):
                    raise NotFoundError("session_not_found")
                return issue
            if delivery:
                return NextQuestionPending(
                    sense_id=delivery.sense_id,
                    recommended_type=delivery.question_format,
                    task_id=delivery.task_id,
                    delivery_id=delivery.id,
                )
    if state.cursor >= len(state.queue):
        return NextQuestionExhausted()

    item = state.queue[state.cursor]
    recommended_type = choose_format(item.mastery, f"{item.sense_id}:{session_id}")
    submission = None
    issue_was_new = not state.issue
    pending_issue = state.issue if state.issue else None
    lease_expired = (
        pending_issue is not None
        and pending_issue.get("state") == "generation_pending"
        and pending_issue.get("lease_until", "") <= datetime.now(UTC).isoformat()
    )
    if issue_was_new:
        reserved = await session_store.reserve_issue(
            redis,
            session_id,
            {
                "state": "generation_pending",
                "sense_id": item.sense_id,
                "recommended_type": recommended_type,
            },
        )
        state = await session_store.get(redis, session_id)
        if state is None:
            raise NotFoundError("session_not_found")
        if state.issue and state.issue["state"] == "ready":
            return state.issue
        if not reserved:
            if state.issue:
                raise ConflictError("question_generation_in_progress")
            raise NotFoundError("session_not_found")

    question = await question_delivery.find_question(
        client, item.sense_id, recommended_type
    )
    if question is None:
        if issue_was_new or lease_expired:
            word_lookup = getattr(client, "word_id_for_sense", None)
            word_id = await word_lookup(item.sense_id) if word_lookup else None
            if word_id is not None:
                if not await session_store.take_generation_slot(redis, user.id):
                    raise ConflictError("question_generation_quota_exceeded")
                submission = await task_service.submit_question_delivery(
                    session,
                    server_work_key=question_pool_work_key(
                        item.sense_id,
                        recommended_type,
                        _QUESTION_GENERATOR_REVISION,
                        _QUESTION_POOL_GENERATION,
                    ),
                    owner_id=user.id,
                    session_id=session_id,
                    sense_id=item.sense_id,
                    question_format=recommended_type,
                    command_id=f"{session_id}:{state.cursor}:{item.sense_id}:{recommended_type}",
                    dispatch={
                        "word_id": word_id,
                        "formats": [recommended_type],
                        "n": 1,
                        "sense_id": item.sense_id,
                    },
                )
                if submission.delivery.snapshot:
                    generated = await client.get_question(
                        submission.delivery.snapshot["questionId"]
                    )
                    if generated is None:
                        raise ConflictError("question_delivery_mismatch")
                    issue = {
                        "state": "ready",
                        **question_delivery.ready_payload(generated, recommended_type),
                    }
                    if not await session_store.replace_issue(redis, session_id, issue):
                        raise NotFoundError("session_not_found")
                    return issue
                if submission.task.status == AsyncTaskStatus.QUEUED:
                    try:
                        pool = await get_arq_pool()
                        await pool.enqueue_job(
                            "generate_question",
                            str(submission.task.id),
                            word_id,
                            [recommended_type],
                            1,
                            None,
                            item.sense_id,
                        )
                    except Exception:  # durable worker reconciliation retries the enqueue
                        pass
                if not await session_store.replace_issue(
                    redis,
                    session_id,
                    {
                        "state": "generation_pending",
                        "sense_id": item.sense_id,
                        "recommended_type": recommended_type,
                        "delivery_id": str(submission.delivery.id),
                        "lease_until": (
                            datetime.now(UTC) + timedelta(seconds=60)
                        ).replace(microsecond=0).isoformat(),
                    },
                ):
                    raise NotFoundError("session_not_found")
        if submission is None:
            raise ConflictError("question_generation_unavailable")
        return NextQuestionPending(
            sense_id=item.sense_id,
            recommended_type=recommended_type,
            task_id=submission.task.id,
            delivery_id=submission.delivery.id,
        )
    if question.sense_id != item.sense_id or question.format != recommended_type:
        raise ConflictError("question_delivery_mismatch")
    issue = {"state": "ready", **question_delivery.ready_payload(question, recommended_type)}
    if not await session_store.replace_issue(redis, session_id, issue):
        raise NotFoundError("session_not_found")
    return issue


@router.post("/answers", response_model=GradeResponse)
async def submit_answer(
    body: AnswerRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
) -> GradeResponse:
    redis = get_redis()
    state = await session_store.get(redis, body.session_id)
    if state is None or state.owner_id != user.id:
        raise NotFoundError("session_not_found")
    node = await require_node_access(session, state.node_id, user, write=False)
    if node.structural_generation != state.scope_generation:
        raise ConflictError("session_scope_changed")
    issue = state.issue
    if (
        not issue
        or issue.get("state") != "ready"
        or issue.get("question_id") != body.question_id
    ):
        raise ConflictError("question_not_issued_for_session")
    question = await client.get_question(body.question_id)
    if question is None or question.sense_id != issue["sense_id"]:
        raise ConflictError("question_not_issued_for_session")
    claimed_issue = await session_store.claim_issue(
        redis, body.session_id, body.question_id
    )
    if claimed_issue is None:
        raise ConflictError("question_not_issued_for_session")

    try:
        if not await session_store.take_grading_slot(redis, user.id):
            raise ConflictError("answer_grading_quota_exceeded")
        response = await service.create_pending_response(
            session,
            user_id=user.id,
            session_id=body.session_id,
            sense_id=question.sense_id,
            question_id=body.question_id,
            raw_answer=body.answer,
            idempotency_key=f"{body.session_id}:{body.question_id}",
        )
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
        await session_store.complete_issue(redis, body.session_id, body.question_id)
        return GradeResponse(
            response_id=response.id,
            grade_status="pending",
            sense_id=question.sense_id,
            task_id=submission.task.id,
        )
    except Exception:
        await session_store.restore_ready_issue(redis, body.session_id, claimed_issue)
        raise
