from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid7

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pycil.database import Base, enum_column


class GenerationStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class WordGeneration(Base):
    __tablename__ = "word_generations"
    __table_args__ = (
        UniqueConstraint("available_id", "target"),
        CheckConstraint("attempts >= 0", name="nonnegative_attempts"),
        Index("ix_generation_queue", "status", "next_attempt_at", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    available_id: Mapped[str] = mapped_column(String(255))
    target: Mapped[str] = mapped_column(String(512))
    word_id: Mapped[int | None] = mapped_column()
    status: Mapped[GenerationStatus] = mapped_column(enum_column(GenerationStatus))
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    error: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
