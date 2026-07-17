"""Durable assistant records. Checkpoint tables are created by Alembic too."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import DateTime, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel

TZDateTime = DateTime(timezone=True)


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


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


class AssistantRun(SQLModel, table=True):
    __tablename__ = "assistant_runs"
    __table_args__ = (
        UniqueConstraint("owner_id", "client_message_id", name="uq_assistant_runs_owner_message"),
        Index("ix_assistant_runs_active_thread", "thread_id", "status"),
    )

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    thread_id: UUID = Field(foreign_key="assistant_threads.id", index=True)
    owner_id: UUID = Field(foreign_key="users.id", index=True)
    client_message_id: UUID
    status: RunStatus = Field(default=RunStatus.PENDING)
    event_cursor: int = Field(default=0)
    error_code: str | None = Field(default=None, max_length=80)
    created_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    updated_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )


class AssistantRunEvent(SQLModel, table=True):
    __tablename__ = "assistant_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_assistant_events_run_sequence"),
    )

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    run_id: UUID = Field(foreign_key="assistant_runs.id", index=True)
    sequence: int
    event_type: str = Field(max_length=40)
    sanitized_payload: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    expires_at: datetime = Field(sa_type=TZDateTime)
    created_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )


class AssistantAction(SQLModel, table=True):
    __tablename__ = "assistant_actions"
    __table_args__ = (Index("ix_assistant_actions_pending_expiry", "status", "expires_at"),)

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    run_id: UUID = Field(foreign_key="assistant_runs.id", index=True)
    owner_id: UUID = Field(foreign_key="users.id", index=True)
    tool: str = Field(max_length=80)
    args_digest: str = Field(max_length=64)
    canonical_args: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    checkpoint_version: str | None = Field(default=None, max_length=255)
    resource_generation: int | None = None
    status: ActionStatus = Field(default=ActionStatus.PENDING)
    expires_at: datetime = Field(sa_type=TZDateTime)
    result: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    correlation_id: UUID
    created_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    updated_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )


class AssistantActionAudit(SQLModel, table=True):
    __tablename__ = "assistant_action_audit"

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    action_id: UUID | None = Field(default=None, foreign_key="assistant_actions.id", index=True)
    actor_id: UUID = Field(foreign_key="users.id", index=True)
    decision: str = Field(max_length=40)
    sanitized_digest: str = Field(max_length=64)
    correlation_id: UUID
    occurred_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
