"""Public response schemas for durable jobs."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pycil.jobs.models import JobStatus


class GenerationCreateRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    job_id: UUID = Field(serialization_alias="jobId")
    status: JobStatus


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    query: str
    status: JobStatus
    result: dict | None = None
    error_code: str | None = Field(default=None, serialization_alias="errorCode")
    attempt: int
