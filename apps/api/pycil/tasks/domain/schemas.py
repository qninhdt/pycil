"""Internal-only DTOs for durable task snapshots and command receipts."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pycil.tasks.domain.vocabulary import AsyncTaskStatus


class AsyncTaskSnapshot(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(default="async-task.v1", alias="schema")
    event_id: UUID = Field(alias="eventId")
    task_id: UUID = Field(alias="taskId")
    kind: str
    status: AsyncTaskStatus
    version: int
    result: dict | None = None
    error_code: str | None = Field(default=None, alias="errorCode")
