"""Public receipt schemas for durable task submission."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GenerationCreateRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: UUID = Field(serialization_alias="taskId")
