"""Job status routes — `GET /jobs/{id}` (poll) and `GET /jobs/{id}/stream` (SSE)."""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlmodel import select

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.services import job_stream_service
from shared.db import Job, UserTermJob

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def get_job(
    job_id: UUID, user: UserDep, session: SessionDep
) -> dict:
    # Ownership: user_term_jobs (term jobs) OR jobs.created_by_user_id (translate/tts/regenerate).
    own = (
        await session.exec(
            select(Job.id)
            .outerjoin(
                UserTermJob,
                (UserTermJob.job_id == Job.id) & (UserTermJob.user_id == user.id),
            )
            .where(
                Job.id == job_id,
                or_(UserTermJob.user_id.is_not(None), Job.created_by_user_id == user.id),
            )
            .limit(1)
        )
    ).first()
    if not own:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "job_forbidden")

    row = (await session.exec(select(Job).where(Job.id == job_id))).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job_not_found")

    result = row.result
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (TypeError, ValueError):
            pass
    return {
        "id": str(row.id),
        "type": row.type,
        "status": row.status,
        "result": result,
        "error": row.error,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("/{job_id}/stream")
async def stream_job(
    job_id: UUID, user: UserDep, session: SessionDep
) -> StreamingResponse:
    generator = job_stream_service.stream_job(
        session, user_id=user.id, job_id=job_id
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
