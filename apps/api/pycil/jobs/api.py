from uuid import UUID

from fastapi import APIRouter, Response
from redis.exceptions import RedisError
from taskiq_redis.exceptions import ResultIsMissingError

from pycil.account.auth import UserId
from pycil.app.dependencies import Runtime
from pycil.app.http import Problem
from pycil.jobs.metadata import owned
from pycil.jobs.schemas import JobStatus

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobStatus)
async def status(job_id: UUID, user: UserId, resources: Runtime, response: Response):
    try:
        if not await owned(resources.redis, str(job_id), user):
            raise Problem(404, "job_not_found")
        backend = resources.broker.result_backend
        try:
            result = await backend.get_result(str(job_id))
        except ResultIsMissingError:
            progress = await backend.get_progress(str(job_id))
            response.headers["Retry-After"] = "2"
            return JobStatus(job_id=job_id, status="running" if progress else "queued")
        if result.is_err:
            return JobStatus(job_id=job_id, status="failed", error="job_failed")
        return JobStatus(job_id=job_id, status="succeeded", result=result.return_value)
    except RedisError, TimeoutError:
        raise Problem(503, "job_status_unavailable") from None
