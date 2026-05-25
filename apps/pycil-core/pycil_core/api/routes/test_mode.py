"""Test mode HTTP API: start run, submit answer, complete, history."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.services import test_mode_service


router = APIRouter(prefix="/decks", tags=["test-mode"])


class StartRunBody(BaseModel):
    question_count: int = 10
    types: list[str] = ["MULTIPLE_CHOICE"]


class SubmitAnswerBody(BaseModel):
    item_id: UUID
    user_answer: str


@router.post("/{deck_id}/test/runs")
async def start_run(
    deck_id: UUID,
    body: StartRunBody,
    user: UserDep,
    session: SessionDep,
) -> dict:
    try:
        return await test_mode_service.start_run(
            session,
            user_id=user.id,
            deck_id=deck_id,
            question_count=body.question_count,
            types=body.types,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/{deck_id}/test/runs/{run_id}/answers")
async def submit_answer(
    deck_id: UUID,
    run_id: UUID,
    body: SubmitAnswerBody,
    user: UserDep,
    session: SessionDep,
) -> dict:
    try:
        return await test_mode_service.submit_answer(
            session,
            user_id=user.id,
            run_id=run_id,
            item_id=body.item_id,
            user_answer=body.user_answer,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.post("/{deck_id}/test/runs/{run_id}/complete")
async def complete_run(
    deck_id: UUID,
    run_id: UUID,
    user: UserDep,
    session: SessionDep,
) -> dict:
    return await test_mode_service.complete_run(
        session, user_id=user.id, run_id=run_id
    )


@router.get("/{deck_id}/test/runs")
async def list_runs(
    deck_id: UUID, user: UserDep, session: SessionDep
) -> dict:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, question_count, correct_count, score_pct,
                       started_at, completed_at
                  FROM test_runs
                 WHERE user_id = :uid AND deck_id = :did
                 ORDER BY started_at DESC
                 LIMIT 50
                """
            ),
            {"uid": user.id, "did": deck_id},
        )
    ).all()
    return {
        "runs": [
            {
                "id": str(r.id),
                "question_count": int(r.question_count),
                "correct_count": int(r.correct_count) if r.correct_count is not None else None,
                "score_pct": float(r.score_pct) if r.score_pct is not None else None,
                "started_at": r.started_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in rows
        ]
    }
