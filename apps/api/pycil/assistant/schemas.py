"""Assistant HTTP contracts; API field names remain camelCase."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ThreadCreate(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=200)


class ThreadRead(BaseModel):
    id: UUID
    title: str
    status: str
    created_at: datetime | None = Field(serialization_alias="createdAt")
    updated_at: datetime | None = Field(serialization_alias="updatedAt")

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    client_message_id: UUID = Field(alias="clientMessageId")
    content: str = Field(min_length=1)

    model_config = {"populate_by_name": True}


class ActionDecision(BaseModel):
    decision: Literal["approve", "reject"]


class RunRead(BaseModel):
    id: UUID
    thread_id: UUID = Field(serialization_alias="threadId")
    status: str
    event_cursor: int = Field(serialization_alias="eventCursor")
    error_code: str | None = Field(default=None, serialization_alias="errorCode")

    model_config = {"from_attributes": True}


class RunEventRead(BaseModel):
    id: UUID
    sequence: int
    event_type: str = Field(serialization_alias="eventType")
    payload: dict

    model_config = {"populate_by_name": True}


class RunRecoveryRead(RunRead):
    events: list[RunEventRead]
