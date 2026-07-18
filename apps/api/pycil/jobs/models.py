"""Pycil-owned durable orchestration records for Lexi generation."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import DateTime, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Column, Field, SQLModel


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WordGeneration(SQLModel, table=True):
    __tablename__ = "word_generations"
    __table_args__ = (Index("ix_word_generations_owner_created", "owner_id", "created_at"),)

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    owner_id: UUID = Field(foreign_key="users.id", index=True)
    query: str
    normalized_query: str = Field(index=True)
    idempotency_key: str | None = Field(default=None, max_length=128)
    status: JobStatus = Field(default=JobStatus.QUEUED)
    result: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    error_code: str | None = None
    attempt: int = Field(default=0)
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
