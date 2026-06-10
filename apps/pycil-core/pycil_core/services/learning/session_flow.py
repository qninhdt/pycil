"""Learning-session flow: start a session and serve the next question.

Builds round-0 state, hydrates per-term ELO, selects terms, and pops the next
question under the session lock. ELO/answer mutation lives in answer_grading.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from shared.db.enums import NodeType
from shared.db.models import Node
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from pycil_core.learning import elo as elo_mod
from pycil_core.learning import term_selection
from pycil_core.schemas.learning import (
    SessionQuestionResponse,
    StartSessionResponse,
)
from pycil_core.services import question_service
from pycil_core.services.learning.session_state import (
    _acquire_lock,
    _load_state,
    _redis,
    _release_lock,
    _save_state,
)

_DEFAULT_ROUND_SIZE = 5


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
