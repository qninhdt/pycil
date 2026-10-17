from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue


class Accepted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    status_url: str

    @classmethod
    def for_job(cls, job_id: str) -> Self:
        return cls(job_id=UUID(job_id), status_url=f"/v1/jobs/{job_id}")


class JobStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    result: JsonValue = None
    error: str | None = None
