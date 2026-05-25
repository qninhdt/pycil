"""Learning session orchestration.

Session state lives in Redis (4h TTL); ELO/interval writes hit Postgres only
on term-reviewed events (Q correct first-answers). Multi-tab races are
serialized with a per-session lock acquired around every state mutation.
"""
from __future__ import annotations

import json
import time
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.config import get_settings
from pycil_core.learning import elo as elo_mod
from pycil_core.learning import term_selection
from pycil_core.learning.intervals import snap_to_ladder
from pycil_core.learning.mastery_levels import level_for_elo
from pycil_core.schemas.learning import (
    SessionQuestionResponse,
    StartSessionResponse,
    SubmitAnswerResponse,
    TermReviewedResult,
)
from pycil_core.services import question_service

_SESSION_TTL_SECONDS = 4 * 60 * 60
_LOCK_TTL_SECONDS = 5
_DEFAULT_ROUND_SIZE = 5
_REQUIRED_CORRECT_FIRSTS = 2


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def _session_key(session_id: str) -> str:
    return f"learning_session:{session_id}"


def _lock_key(session_id: str) -> str:
    return f"session_lock:{session_id}"


async def _acquire_lock(redis: Redis, session_id: str) -> str:
    """SET NX EX lock. Returns request_id; raises 409 on contention."""
    request_id = _uuid.uuid4().hex
    ok = await redis.set(
        _lock_key(session_id), request_id, nx=True, ex=_LOCK_TTL_SECONDS
    )
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
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "session_corrupt"
        ) from e


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
) -> dict[str, Any]:
    """Build the round-0 state. round_queue starts as the full session list."""
    return {
        "id": session_id,
        "user_id": str(user_id),
        "deck_id": str(deck_id),
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


async def _hydrate_initial_elo(
    session: AsyncSession, user_id: UUID, state: dict[str, Any]
) -> None:
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
) -> StartSessionResponse:
    """Pick terms, build state, persist to Redis, return id."""
    deck_row = (
        await session.execute(
            text("SELECT author_id, type FROM nodes WHERE id = :id"),
            {"id": deck_id},
        )
    ).first()
    if not deck_row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deck_not_found")
    if deck_row.author_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "deck_forbidden")
    if deck_row.type != "DECK":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "node_not_deck")

    definition_ids = await term_selection.select_definition_ids(
        session, user_id, deck_id, session_size
    )
    if not definition_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no_terms_to_study")

    session_id = str(uuid4())
    state = _initial_state(session_id, user_id, deck_id, definition_ids)
    await _hydrate_initial_elo(session, user_id, state)

    redis = _redis()
    try:
        await _save_state(redis, session_id, state)
    finally:
        await redis.aclose()

    return StartSessionResponse(
        session_id=session_id,
        deck_id=deck_id,
        selected_count=len(definition_ids),
    )


def _next_round_queue(state: dict) -> list[int]:
    """Build the next round's queue from terms not yet completed."""
    return [
        did
        for did in state["definition_ids"]
        if not state["term_tracking"][str(did)]["completed"]
    ]


async def next_question(
    session: AsyncSession, user_id: UUID, session_id: str
) -> SessionQuestionResponse:
    """Pop next term, fetch/generate its MCQ, return payload."""
    redis = _redis()
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
        fetched = await question_service.get_or_generate(
            session, definition_id, "easy"
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
    nrd = datetime.now(tz=timezone.utc) + timedelta(seconds=interval_seconds)
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
    lapsed = (
        datetime.now(tz=timezone.utc) - row.last_review_date
    ).total_seconds()
    return (lapsed, float(row.interval_seconds or 0))


async def submit_answer(
    session: AsyncSession,
    user_id: UUID,
    session_id: str,
    question_id: UUID,
    selected_index: int,
) -> SubmitAnswerResponse:
    from shared.questions.multiple_choice import MultipleChoiceQuestion

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
        if q_row.type != "MULTIPLE_CHOICE":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "unsupported_question_type"
            )
        data = q_row.data
        if isinstance(data, str):
            data = json.loads(data)

        check = MultipleChoiceQuestion.check_answer(
            data, {"selected_index": selected_index}
        )
        correct = check.correct
        correct_idx = data.get("correct_index", 0)

        definition_id = int(state["current_definition_id"])
        tracking = state["term_tracking"][str(definition_id)]
        was_first = tracking["is_first_attempt"]

        if correct:
            if was_first:
                tracking["correct_firsts"] += 1
            tracking["is_first_attempt"] = True
            # pop from queue.
            state["round_queue"] = state["round_queue"][1:]
        else:
            tracking["is_first_attempt"] = False
            # leave in queue (front) so client retries.

        term_reviewed: TermReviewedResult | None = None
        if tracking["correct_firsts"] >= _REQUIRED_CORRECT_FIRSTS and not tracking["completed"]:
            tracking["completed"] = True
            elo_old = int(tracking["elo_at_start"])
            R = elo_mod.realized_score(
                tracking["correct_firsts"], _REQUIRED_CORRECT_FIRSTS
            )
            E = elo_mod.expected_score(elo_old, [elo_mod.INITIAL_ELO])
            lapsed, interval_old = await _previous_review(
                session, user_id, definition_id
            )
            T = elo_mod.lapsed_time_factor(lapsed, interval_old)
            d = elo_mod.elo_delta(R, E, T)
            elo_new = elo_mod.new_elo(elo_old, d)
            new_interval_raw = elo_mod.new_interval_seconds(
                elo_old, elo_new, interval_old
            )
            new_interval = snap_to_ladder(new_interval_raw)
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
            # Drop from any pending round_queue entry.
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

        return SubmitAnswerResponse(
            correct=correct,
            explanation=check.explanation,
            correct_index=correct_idx,
            round_complete=round_complete,
            session_complete=session_complete,
            term_reviewed=term_reviewed,
        )
    finally:
        await _release_lock(redis, session_id, request_id)
        await redis.aclose()
