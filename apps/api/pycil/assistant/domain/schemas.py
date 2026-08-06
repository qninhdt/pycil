"""Assistant HTTP contracts; API field names remain camelCase."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field


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
    """One persisted run event, as replayed by the two non-streaming reads.

    Both aliases are declared for a reason. `serialization_alias` alone names only
    the *output* field, so a keyword built from the camelCase name failed
    validation and the endpoint answered 500 on its first row. And `payload` is
    stored as `sanitized_payload`, so validating straight off the ORM row needs
    that name accepted too — which is what lets the router hand over the row
    itself instead of restating every field at two call sites.
    """

    id: UUID
    # `sequence` is only unique *within* a run, because it is that run's
    # `event_cursor`. The thread read returns every run's events in one list, so a
    # consumer that ordered or de-duplicated on `sequence` alone would collide the
    # second turn's first event with the first turn's. Carrying the run makes the
    # real key `(runId, sequence)`, and it is also the only way a client learns a
    # run id at all — which is what the recovery endpoint needs.
    run_id: UUID = Field(
        validation_alias=AliasChoices("run_id", "runId"),
        serialization_alias="runId",
    )
    sequence: int
    event_type: str = Field(
        validation_alias=AliasChoices("event_type", "eventType"),
        serialization_alias="eventType",
    )
    payload: dict = Field(validation_alias=AliasChoices("payload", "sanitized_payload"))

    model_config = {"populate_by_name": True, "from_attributes": True}


class RunRecoveryRead(RunRead):
    events: list[RunEventRead]
