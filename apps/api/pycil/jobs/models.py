"""Pycil-owned durable orchestration records for Lexi generation."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import DateTime, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WordGeneration(SQLModel, table=True):
    __tablename__ = "word_generations"
    __table_args__ = (
        Index("ix_word_generations_owner_created", "owner_id", "created_at"),
        Index("ix_word_generations_claimable", "status", "next_attempt_at"),
    )

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    owner_id: UUID = Field(foreign_key="users.id", index=True)
    query: str
    normalized_query: str = Field(index=True)
    idempotency_key: str | None = Field(default=None, max_length=128)
    # Keep the ORM aligned with migration 0010, which deliberately stores the
    # lifecycle as text rather than creating a PostgreSQL enum type.
    status: JobStatus = Field(
        default=JobStatus.QUEUED,
        sa_column=Column(Text, nullable=False, server_default=text("'queued'")),
    )
    result: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    error_code: str | None = None
    attempt: int = Field(default=0)
    max_attempts: int = Field(default=4)
    lease_owner: str | None = Field(default=None, max_length=128)
    lease_token: str | None = Field(default=None, max_length=64)
    lease_fence: int = Field(default=0)
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
