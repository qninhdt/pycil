"""Learning session orchestration.

Session state lives in Redis (4h TTL); ELO/interval writes hit Postgres only
on term-reviewed events (Q correct first-answers). Multi-tab races are
serialized with a per-session lock acquired around every state mutation.
"""

from __future__ import annotations

import json
import time
import uuid as _uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from redis.asyncio import Redis
from shared.db.enums import NodeType
from shared.db.models import Node
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from pycil_core.learning import elo as elo_mod
from pycil_core.learning import term_selection
from pycil_core.learning.intervals import snap_to_ladder
from pycil_core.learning.mastery_levels import level_for_elo
from pycil_core.schemas.grading import AsyncGradePending
from pycil_core.schemas.learning import (
    SessionQuestionResponse,
    StartSessionResponse,
    SubmitAnswerResponse,
    TermReviewedResult,
)
from pycil_core.services import question_service
from pycil_core.services.redis_pool import get_redis

_SESSION_TTL_SECONDS = 4 * 60 * 60
_LOCK_TTL_SECONDS = 30
_DEFAULT_ROUND_SIZE = 5
_REQUIRED_CORRECT_FIRSTS = 2


def _redis() -> Redis:
    return get_redis()


def _session_key(session_id: str) -> str:
    return f"learning_session:{session_id}"


def _lock_key(session_id: str) -> str:
    return f"session_lock:{session_id}"


async def _acquire_lock(redis: Redis, session_id: str) -> str:
    """SET NX EX lock. Returns request_id; raises 409 on contention."""
    request_id = _uuid.uuid4().hex
    ok = await redis.set(_lock_key(session_id), request_id, nx=True, ex=_LOCK_TTL_SECONDS)
    if not ok:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "session_busy"},
        )
    return request_id


_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
else
  return 0
end
"""


async def _release_lock(redis: Redis, session_id: str, request_id: str) -> None:
    await redis.eval(_RELEASE_LUA, 1, _lock_key(session_id), request_id)


async def _load_state(redis: Redis, session_id: str) -> dict[str, Any]:
    raw = await redis.get(_session_key(session_id))
    if not raw:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session_not_found")
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "session_corrupt") from e


async def _save_state(redis: Redis, session_id: str, state: dict) -> None:
    await redis.set(
        _session_key(session_id),
        json.dumps(state, default=str),
        ex=_SESSION_TTL_SECONDS,
    )


def _initial_state(
    session_id: str,
    user_id: UUID,
    deck_id: UUID,
    definition_ids: list[int],
    theme_id: str | None = None,
) -> dict[str, Any]:
    """Build the round-0 state. round_queue starts as the full session list."""
    return {
        "id": session_id,
        "user_id": str(user_id),
        "deck_id": str(deck_id),
        "theme_id": theme_id,
        "definition_ids": definition_ids,
        "term_tracking": {
            str(did): {
                "correct_firsts": 0,
                "is_first_attempt": True,
                "elo_at_start": elo_mod.INITIAL_ELO,
                "completed": False,
            }
            for did in definition_ids
        },
        "round_index": 0,
        "round_queue": list(definition_ids),
        "current_question_id": None,
        "current_definition_id": None,
        "started_at": time.time(),
    }


async def _hydrate_initial_elo(session: AsyncSession, user_id: UUID, state: dict[str, Any]) -> None:
    """Replace the 1000 default with the user's stored ELO if any."""
    if not state["definition_ids"]:
        return
    rows = (
        await session.execute(
            text(
                """
                SELECT definition_id, mastery_score AS elo
                FROM user_term_stats
                WHERE user_id = :uid AND definition_id = ANY(:ids)
                """
            ),
            {"uid": user_id, "ids": state["definition_ids"]},
        )
    ).all()
    for r in rows:
        key = str(r.definition_id)
        if key in state["term_tracking"]:
            state["term_tracking"][key]["elo_at_start"] = int(r.elo)


async def start_session(
    session: AsyncSession,
    user_id: UUID,
    deck_id: UUID,
    session_size: int,
    theme_id: str | None = None,
) -> StartSessionResponse:
    """Pick terms, build state, persist to Redis, return id."""
    from pycil_core.services import theme_service

    if not theme_service.is_valid(theme_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown_theme")

    deck_row = (
        await session.exec(select(Node.author_id, Node.type).where(Node.id == deck_id))
    ).first()
    if not deck_row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deck_not_found")
    if deck_row.author_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "deck_forbidden")
    if deck_row.type != NodeType.DECK:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "node_not_deck")

    definition_ids = await term_selection.select_definition_ids(
        session, user_id, deck_id, session_size
    )
    if not definition_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no_terms_to_study")

    session_id = str(uuid4())
    state = _initial_state(session_id, user_id, deck_id, definition_ids, theme_id)
    await _hydrate_initial_elo(session, user_id, state)

    redis = _redis()
    try:
        await _save_state(redis, session_id, state)
    finally:
        await redis.aclose()

    # Fire-and-forget bank prewarm for the selected terms so subsequent
    # next_question calls hit ready questions instead of waiting on generation.
    # Best-effort: a prewarm enqueue failure must not block session start.
    from pycil_core.services import question_bank_service

    try:
        await question_bank_service.enqueue_prewarm(definition_ids, user_id)
    except Exception:  # noqa: BLE001
        pass

    return StartSessionResponse(
        session_id=session_id,
        deck_id=deck_id,
        selected_count=len(definition_ids),
    )


def _next_round_queue(state: dict) -> list[int]:
    """Build the next round's queue from terms not yet completed."""
    return [
        did for did in state["definition_ids"] if not state["term_tracking"][str(did)]["completed"]
    ]


def _question_type_for(definition_id: int) -> str:
    """Pick the question type the learn loop serves for a definition.

    Currently always MULTIPLE_CHOICE. The learn-loop submit path is index-only
    (selected_index) and the WRITE/FILL answer UIs are not yet mounted in the
    session, so serving a non-MCQ type here would render a question the user
    cannot answer. WRITE/FILL stay fully built + tested at the service/worker
    layer (generation, grading, registry dispatch); the learn loop begins
    serving them once the generic {answer: dict} submit contract + per-type
    answer UIs land. Kept as a function (not inlined) so enabling type variation
    is a one-line change to a stable, per-definition deterministic pick:

        types = registry.all_types(); return types[definition_id % len(types)]

    Deterministic-by-definition (not rotating) is the required shape so the
    bank cache hits and a seed can pin a definition to a known type.
    """
    return "MULTIPLE_CHOICE"


async def next_question(
    session: AsyncSession, user_id: UUID, session_id: str
) -> SessionQuestionResponse:
    """Pop next term, fetch/generate its MCQ, return payload.

    LLM enqueue / question fetch happens BEFORE acquiring the per-session
    lock so the lock guards only Redis state mutation — eliminates lock
    starvation during generation latency.
    """
    redis = _redis()
    # Read state outside the lock to determine which definition to fetch.
    peek = await _load_state(redis, session_id)
    if peek["user_id"] != str(user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "session_forbidden")
    peek_queue: list[int] = list(peek.get("round_queue") or [])
    if not peek_queue:
        peek_queue = _next_round_queue(peek)[:_DEFAULT_ROUND_SIZE]
    peek_definition_id = int(peek_queue[0]) if peek_queue else None

    fetched = None
    if peek_definition_id is not None:
        fetched = await question_service.get_or_generate(
            session, peek_definition_id, "easy", user_id,
            _question_type_for(peek_definition_id),
        )

    request_id = await _acquire_lock(redis, session_id)
    try:
        state = await _load_state(redis, session_id)
        if state["user_id"] != str(user_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "session_forbidden")

        # Replenish round if empty.
        if not state["round_queue"]:
            remaining = _next_round_queue(state)
            if not remaining:
                state["current_question_id"] = None
                state["current_definition_id"] = None
                await _save_state(redis, session_id, state)
                return SessionQuestionResponse(
                    status="session_complete",
                    round_index=state["round_index"],
                )
            # Fresh round.
            state["round_index"] += 1
            state["round_queue"] = remaining[:_DEFAULT_ROUND_SIZE]

        definition_id = int(state["round_queue"][0])
        # If the queue head shifted while we fetched, refetch under lock.
        if fetched is None or definition_id != peek_definition_id:
            fetched = await question_service.get_or_generate(
                session, definition_id, "easy", user_id,
                _question_type_for(definition_id),
            )
        if fetched.status != "ready" or fetched.question is None:
            # Generation pending; client should retry.
            await _save_state(redis, session_id, state)
            return SessionQuestionResponse(
                status="pending",
                round_index=state["round_index"],
                round_position=0,
                round_size=len(state["round_queue"]),
            )

        state["current_question_id"] = str(fetched.question.id)
        state["current_definition_id"] = definition_id
        await _save_state(redis, session_id, state)

        from pycil_core.services import theme_service

        # Per-question theme: a concrete session theme stays stable; themed-pool
        # mode (no session theme) rotates by definition_id so each term shows a
        # different, deterministic theme. Presentation only — never grading.
        question_theme = theme_service.rotate_theme_id(
            state.get("theme_id"), definition_id
        )

        return SessionQuestionResponse(
            question={
                "id": str(fetched.question.id),
                "definition_id": fetched.question.definition_id,
                "type": fetched.question.type,
                "data": fetched.question.data,
            },
            status="ready",
            round_index=state["round_index"],
            round_position=0,
            round_size=len(state["round_queue"]),
            theme=question_theme,
        )
    finally:
        await _release_lock(redis, session_id, request_id)
        await redis.aclose()


async def _persist_review(
    session: AsyncSession,
    user_id: UUID,
    definition_id: int,
    elo_old: int,
    elo_new: int,
    interval_seconds: int,
) -> datetime:
    """UPSERT user_term_stats with new ELO + next_review_date. Returns NRD."""
    nrd = datetime.now(tz=UTC) + timedelta(seconds=interval_seconds)
    await session.execute(
        text(
            """
            INSERT INTO user_term_stats (
                user_id, definition_id, mastery_score, last_review_date,
                next_review_date, interval_seconds, mastery_level
            )
            VALUES (
                :uid, :did, :elo, NOW(), :nrd, :interval, :level
            )
            ON CONFLICT (user_id, definition_id) DO UPDATE SET
                mastery_score = EXCLUDED.mastery_score,
                last_review_date = EXCLUDED.last_review_date,
                next_review_date = EXCLUDED.next_review_date,
                interval_seconds = EXCLUDED.interval_seconds,
                mastery_level = EXCLUDED.mastery_level,
                updated_at = NOW()
            """
        ),
        {
            "uid": user_id,
            "did": definition_id,
            "elo": elo_new,
            "nrd": nrd,
            "interval": interval_seconds,
            "level": level_for_elo(elo_new),
        },
    )
    await session.commit()
    return nrd


async def _previous_review(
    session: AsyncSession, user_id: UUID, definition_id: int
) -> tuple[float | None, float]:
    """(lapsed_seconds, interval_old) for the ELO calc."""
    row = (
        await session.execute(
            text(
                """
                SELECT last_review_date, interval_seconds
                FROM user_term_stats
                WHERE user_id = :uid AND definition_id = :did
                """
            ),
            {"uid": user_id, "did": definition_id},
        )
    ).first()
    if not row or row.last_review_date is None:
        return (None, 0.0)
    lapsed = (datetime.now(tz=UTC) - row.last_review_date).total_seconds()
    return (lapsed, float(row.interval_seconds or 0))


async def _apply_answer_outcome(
    session: AsyncSession,
    redis: Redis,
    *,
    user_id: UUID,
    session_id: str,
    state: dict,
    definition_id: int,
    correct: bool,
) -> tuple[TermReviewedResult | None, bool, bool, bool]:
    """Apply a graded answer to session state + ELO + XP. Caller MUST hold the
    session lock. Shared by the sync (submit_answer) and async
    (apply_async_verdict) paths so the ELO/queue/XP logic stays single-sourced.

    Returns (term_reviewed, round_complete, session_complete, was_first).
    """
    from pycil_core.services import gamification_service

    tracking = state["term_tracking"][str(definition_id)]
    was_first = tracking["is_first_attempt"]

    if correct:
        if was_first:
            tracking["correct_firsts"] += 1
        tracking["is_first_attempt"] = True
        state["round_queue"] = state["round_queue"][1:]
    else:
        tracking["is_first_attempt"] = False

    term_reviewed: TermReviewedResult | None = None
    if tracking["correct_firsts"] >= _REQUIRED_CORRECT_FIRSTS and not tracking["completed"]:
        tracking["completed"] = True
        elo_old = int(tracking["elo_at_start"])
        R = elo_mod.realized_score(tracking["correct_firsts"], _REQUIRED_CORRECT_FIRSTS)
        E = elo_mod.expected_score(elo_old, [elo_mod.INITIAL_ELO])
        lapsed, interval_old = await _previous_review(session, user_id, definition_id)
        T = elo_mod.lapsed_time_factor(lapsed, interval_old)
        d = elo_mod.elo_delta(R, E, T)
        elo_new = elo_mod.new_elo(elo_old, d)
        new_interval = snap_to_ladder(
            elo_mod.new_interval_seconds(elo_old, elo_new, interval_old)
        )
        nrd = await _persist_review(
            session, user_id, definition_id, elo_old, elo_new, new_interval
        )
        term_reviewed = TermReviewedResult(
            definition_id=definition_id,
            elo_old=elo_old,
            elo_new=elo_new,
            elo_delta=d,
            next_review_date=nrd,
            interval_seconds=new_interval,
            mastery_level=level_for_elo(elo_new),
        )
        state["round_queue"] = [
            did for did in state["round_queue"] if int(did) != definition_id
        ]

    round_complete = len(state["round_queue"]) == 0
    session_complete = round_complete and all(
        t["completed"] for t in state["term_tracking"].values()
    )

    state["current_question_id"] = None
    state["current_definition_id"] = None
    await _save_state(redis, session_id, state)

    xp_delta = (
        gamification_service.XP_DELTA["correct_new"]
        if correct and was_first
        else gamification_service.XP_DELTA["correct_review"]
        if correct
        else gamification_service.XP_DELTA["wrong"]
    )
    await gamification_service.award_xp(session, user_id=user_id, delta=xp_delta)
    await gamification_service.tick_streak(session, user_id=user_id)
    if term_reviewed is not None:
        await gamification_service.check_badges(session, user_id=user_id)

    return term_reviewed, round_complete, session_complete, was_first


async def submit_answer(
    session: AsyncSession,
    user_id: UUID,
    session_id: str,
    question_id: UUID,
    selected_index: int,
    answer: dict | None = None,
) -> SubmitAnswerResponse | AsyncGradePending:
    """Grade a submitted answer.

    Sync types (MCQ, Fill) grade inline and mutate session state immediately.
    Async types (Write, ``requires_server_grading``) enqueue a grade job and
    return ``AsyncGradePending`` WITHOUT mutating session state — ELO/XP and
    queue advance happen later in ``apply_async_verdict`` once the verdict
    resolves. ``answer`` is the generic plugin payload; ``selected_index`` is the
    MCQ back-compat shape (the {answer: dict} request migration lands in phase 5).
    """
    from shared.questions import registry

    from pycil_core.services import async_grade_service

    redis = _redis()
    request_id = await _acquire_lock(redis, session_id)
    try:
        state = await _load_state(redis, session_id)
        if state["user_id"] != str(user_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "session_forbidden")
        if state.get("current_question_id") != str(question_id):
            raise HTTPException(status.HTTP_409_CONFLICT, "question_mismatch")

        # Load question.
        q_row = (
            await session.execute(
                text(
                    "SELECT id, type::text AS type, data, definition_id "
                    "FROM questions WHERE id = :id"
                ),
                {"id": question_id},
            )
        ).first()
        if not q_row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "question_not_found")
        if not registry.is_registered(q_row.type):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported_question_type")
        data = q_row.data
        if isinstance(data, str):
            data = json.loads(data)

        plugin = registry.get(q_row.type)

        # Async grading: enqueue + return pending. Do NOT advance session state;
        # apply_async_verdict commits ELO/XP/queue under the lock once graded.
        if plugin.requires_server_grading:
            user_answer = str((answer or {}).get("user_answer", ""))
            return await async_grade_service.enqueue_grade(
                session,
                user_id=user_id,
                question_id=question_id,
                user_answer=user_answer,
                session_id=session_id,
            )

        answer_payload = answer if answer is not None else {"selected_index": selected_index}
        check = plugin.check_answer(data, answer_payload)
        correct = check.correct
        correct_idx = check.reveal.get("correct_index", data.get("correct_index", 0))

        definition_id = int(state["current_definition_id"])
        term_reviewed, round_complete, session_complete, _was_first = (
            await _apply_answer_outcome(
                session,
                redis,
                user_id=user_id,
                session_id=session_id,
                state=state,
                definition_id=definition_id,
                correct=correct,
            )
        )

        return SubmitAnswerResponse(
            correct=correct,
            score=check.score,
            feedback=check.feedback,
            reveal=check.reveal,
            explanation=check.explanation,
            correct_index=correct_idx,
            round_complete=round_complete,
            session_complete=session_complete,
            term_reviewed=term_reviewed,
        )
    finally:
        await _release_lock(redis, session_id, request_id)
        await redis.aclose()


async def apply_async_verdict(
    session: AsyncSession,
    user_id: UUID,
    session_id: str,
    response_id: UUID,
) -> SubmitAnswerResponse:
    """Apply an async (LLM-judge) verdict to session state + ELO/XP.

    Called by the FE after the SSE verdict frame resolves. Runs under the
    session lock and reuses ``_apply_answer_outcome`` so async grading matches
    the sync path exactly. Exactly-once: atomically claims the response row
    (``elo_applied`` FALSE→TRUE) — a second call no-ops and returns the verdict
    without re-crediting ELO. The claim commits atomically with the ELO write.
    """
    redis = _redis()
    request_id = await _acquire_lock(redis, session_id)
    try:
        row = (
            await session.execute(
                text(
                    """
                    SELECT user_id, is_correct, grade_status, elo_applied,
                           session_id, grade_score, grade_feedback
                      FROM responses WHERE id = :rid
                    """
                ),
                {"rid": response_id},
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "response_not_found")
        if str(row.user_id) != str(user_id) or row.session_id != session_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "response_forbidden")
        if row.grade_status != "graded":
            raise HTTPException(status.HTTP_409_CONFLICT, "grade_pending")

        correct = bool(row.is_correct)
        score = (
            float(row.grade_score)
            if row.grade_score is not None
            else (1.0 if correct else 0.0)
        )

        # Idempotent claim: only the first caller flips elo_applied + applies.
        claimed = (
            await session.execute(
                text(
                    "UPDATE responses SET elo_applied = TRUE "
                    "WHERE id = :rid AND elo_applied = FALSE RETURNING id"
                ),
                {"rid": response_id},
            )
        ).first()
        if claimed is None:
            await session.commit()
            return SubmitAnswerResponse(
                correct=correct,
                score=score,
                feedback=row.grade_feedback,
                explanation=row.grade_feedback,
                round_complete=False,
                session_complete=False,
                term_reviewed=None,
            )

        state = await _load_state(redis, session_id)
        if state["user_id"] != str(user_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "session_forbidden")
        definition_id = int(state["current_definition_id"])
        term_reviewed, round_complete, session_complete, _ = (
            await _apply_answer_outcome(
                session,
                redis,
                user_id=user_id,
                session_id=session_id,
                state=state,
                definition_id=definition_id,
                correct=correct,
            )
        )
        await session.commit()
        return SubmitAnswerResponse(
            correct=correct,
            score=score,
            feedback=row.grade_feedback,
            explanation=row.grade_feedback,
            round_complete=round_complete,
            session_complete=session_complete,
            term_reviewed=term_reviewed,
        )
    finally:
        await _release_lock(redis, session_id, request_id)
        await redis.aclose()
