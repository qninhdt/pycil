"""Regenerate a question for a definition.

Bumps `variant_seed` and enqueues a fresh `generate_question` job. FE
listens via existing SSE on the returned job_id.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text

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

    owns = (
        await session.execute(
            text(
                """
                SELECT 1
                  FROM definitions d
                  JOIN deck_definitions dd ON dd.definition_id = d.id
                  JOIN nodes n ON n.id = dd.deck_id
                 WHERE d.id = :did AND n.author_id = :uid
                 LIMIT 1
                """
            ),
            {"did": definition_id, "uid": user.id},
        )
    ).first()
    if not owns:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_owner")

    await session.execute(
        text(
            "DELETE FROM questions "
            "WHERE definition_id = :did AND type = CAST(:t AS question_type)"
        ),
        {"did": definition_id, "t": type},
    )

    job = (
        await session.execute(
            text(
                """
                INSERT INTO jobs (type, status, payload, created_by_user_id)
                VALUES ('generate_question', 'queued',
                        CAST(:p AS jsonb), :uid)
                RETURNING id
                """
            ),
            {
                "p": json.dumps({"definition_id": definition_id, "type": type}),
                "uid": user.id,
            },
        )
    ).one()
    await session.commit()
    return {"job_id": str(job.id)}
