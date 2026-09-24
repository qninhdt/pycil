"""Durable assistant thread ownership."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, text
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)


class AssistantThread(SQLModel, table=True):
    __tablename__ = "assistant_threads"

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    owner_id: UUID = Field(foreign_key="users.id", index=True)
    title: str = Field(default="New conversation", max_length=200)
    status: str = Field(default="active", max_length=20)
    retention_deadline: datetime = Field(sa_type=TZDateTime)
    created_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    updated_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )


