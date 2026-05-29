"""Regenerate a question for a definition.

Bumps `variant_seed` and enqueues a fresh `generate_question` job. FE
listens via existing SSE on the returned job_id.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from shared.db import DeckDefinition, Definition, Job, Node, Question
from shared.db.enums import QuestionType
from sqlalchemy import delete, select

from pycil_core.api.deps import SessionDep, UserDep

router = APIRouter(prefix="/definitions", tags=["questions"])


@router.post("/{definition_id}/question/regenerate")
async def regenerate_question(
    definition_id: int,
    user: UserDep,
    session: SessionDep,
    type: str = Query(default="MULTIPLE_CHOICE"),
) -> dict:
    if type not in ("MULTIPLE_CHOICE", "WRITE", "FILL_IN_BLANK"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported_type")
    question_type = QuestionType(type)

    owns = (
        await session.exec(
            select(Definition.id)
            .join(DeckDefinition, DeckDefinition.definition_id == Definition.id)
            .join(Node, Node.id == DeckDefinition.deck_id)
            .where(Definition.id == definition_id, Node.author_id == user.id)
            .limit(1)
        )
    ).first()
    if not owns:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_owner")

    await session.exec(
        delete(Question).where(
            Question.definition_id == definition_id,
            Question.type == question_type,
        )
    )

    job = Job(
        type="generate_question",
        status="queued",
        payload={"definition_id": definition_id, "type": type},
        created_by_user_id=user.id,
    )
    session.add(job)
    await session.flush()
    await session.commit()
    return {"job_id": str(job.id)}
