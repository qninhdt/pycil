"""SQLModel records for the durable async task registry and transactional outbox."""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel


class AsyncTaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class OutboxStatus(str, Enum):
    PENDING = "pending"
    LEASED = "leased"
    DELIVERED = "delivered"
    DEAD_LETTER = "dead_letter"


class AsyncTask(SQLModel, table=True):
    __tablename__ = "async_tasks"
    __table_args__ = (
        Index("ix_async_tasks_claimable", "status", "next_attempt_at"),
        Index(
            "uq_async_tasks_active_work",
            "kind",
            "work_key",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running', 'succeeded')"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    kind: str = Field(max_length=80, index=True)
    # Work keys are server-only HMAC-backed values; never serialize them.
    work_key: str = Field(max_length=512)
    status: AsyncTaskStatus = Field(
        default=AsyncTaskStatus.QUEUED,
        sa_column=Column(Text, nullable=False, server_default=text("'queued'")),
    )
    version: int = Field(default=1, sa_column_kwargs={"server_default": text("1")})
    result: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    error_code: str | None = Field(default=None, max_length=120)
    attempt: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    max_attempts: int = Field(default=4, sa_column_kwargs={"server_default": text("4")})
    lease_owner: str | None = Field(default=None, max_length=128)
    lease_token: str | None = Field(default=None, max_length=64)
    lease_fence: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    lease_expires_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    next_attempt_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    created_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class AsyncTaskInterest(SQLModel, table=True):
    __tablename__ = "async_task_interests"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "requester_id", "provenance", name="uq_task_interest_provenance"
        ),
        Index("ix_async_task_interests_requester", "requester_id", "expires_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    task_id: UUID = Field(foreign_key="async_tasks.id", index=True)
    requester_id: UUID = Field(foreign_key="users.id", index=True)
    provenance: str = Field(max_length=120)
    expires_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    revoked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class AsyncTaskDelivery(SQLModel, table=True):
    """Private session projection of a shareable task's terminal result."""

    __tablename__ = "async_task_deliveries"
    __table_args__ = (
        UniqueConstraint("task_id", "session_id", name="uq_task_delivery_session"),
        Index("ix_async_task_deliveries_owner_session", "owner_id", "session_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    task_id: UUID = Field(foreign_key="async_tasks.id", index=True)
    session_id: str = Field(max_length=128)
    owner_id: UUID = Field(foreign_key="users.id", index=True)
    sense_id: int
    question_format: str = Field(max_length=80)
    snapshot: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    resolved_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class AsyncTaskEvent(SQLModel, table=True):
    __tablename__ = "async_task_events"
    __table_args__ = (UniqueConstraint("task_id", "version", name="uq_task_event_version"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    task_id: UUID = Field(foreign_key="async_tasks.id", index=True)
    version: int
    schema_name: str = Field(default="async-task.v1", max_length=40)
    snapshot: dict = Field(sa_column=Column(JSONB, nullable=False))
    created_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class AsyncTaskOutbox(SQLModel, table=True):
    __tablename__ = "async_task_outbox"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_async_task_outbox_event"),
        Index("ix_async_task_outbox_claimable", "status", "next_attempt_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    event_id: UUID = Field(foreign_key="async_task_events.id", index=True)
    channel: str = Field(max_length=160)
    payload: dict = Field(sa_column=Column(JSONB, nullable=False))
    status: OutboxStatus = Field(
        default=OutboxStatus.PENDING,
        sa_column=Column(Text, nullable=False, server_default=text("'pending'")),
    )
    attempt: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    max_attempts: int = Field(default=12, sa_column_kwargs={"server_default": text("12")})
    lease_owner: str | None = Field(default=None, max_length=128)
    lease_expires_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    next_attempt_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": text("NOW()")},
    )
    delivered_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": text("NOW()")},
    )


class AsyncCommandReceipt(SQLModel, table=True):
    __tablename__ = "async_command_receipts"
    __table_args__ = (
        UniqueConstraint(
            "requester_id", "command_kind", "command_id", name="uq_async_command_receipt"
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    requester_id: UUID = Field(foreign_key="users.id", index=True)
    command_kind: str = Field(max_length=80)
    command_id: str = Field(max_length=128)
    task_id: UUID = Field(foreign_key="async_tasks.id", index=True)
    delivery_id: UUID | None = Field(default=None, index=True)
    created_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": text("NOW()")},
    )
