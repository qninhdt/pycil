"""Owner-scoped durable job inspection endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import NotFoundError
from pycil.db.session import get_session
from pycil.jobs import service
from pycil.jobs.schemas import JobRead

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(
    job_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> JobRead:
    record = await service.get_generation(session, job_id, user.id)
    if record is None:
        raise NotFoundError("job_not_found")
    return JobRead.model_validate(record)
