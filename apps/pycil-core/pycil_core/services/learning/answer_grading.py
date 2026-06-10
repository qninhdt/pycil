"""Learning-session answer grading: apply a graded answer to ELO/XP/queue.

Owns the single-sourced outcome logic shared by the sync (submit_answer) and
async LLM-judge (apply_async_verdict) paths, plus the user_term_stats persist
and prior-review lookup feeding the ELO calc. Runs under the session lock held
by the caller / acquired here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.learning import elo as elo_mod
from pycil_core.learning.intervals import snap_to_ladder
from pycil_core.learning.mastery_levels import level_for_elo
from pycil_core.schemas.grading import AsyncGradePending
from pycil_core.schemas.learning import (
    SubmitAnswerResponse,
    TermReviewedResult,
)
from pycil_core.services.learning.session_state import (
    _acquire_lock,
    _load_state,
    _redis,
    _release_lock,
    _save_state,
)

_REQUIRED_CORRECT_FIRSTS = 2


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
    MCQ back-compat shape (dual-shape is an intentional, permanent contract).
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
