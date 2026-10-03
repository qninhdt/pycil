from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from pycil.database import Base, enum_column


class Rating(StrEnum):
    AGAIN = "AGAIN"
    HARD = "HARD"
    GOOD = "GOOD"
    EASY = "EASY"


class SenseMemory(Base):
    __tablename__ = "sense_memory"
    __table_args__ = (
        CheckConstraint("stability > 0 AND difficulty > 0", name="positive_memory"),
        CheckConstraint("review_count > 0 AND lapse_count >= 0", name="valid_counts"),
        Index("ix_memory_user_due", "user_id", "due_at", "sense_id"),
        Index("ix_memory_user_stability", "user_id", "stability", "sense_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    sense_id: Mapped[int] = mapped_column(
        ForeignKey("lexi.senses.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    stability: Mapped[float] = mapped_column()
    difficulty: Mapped[float] = mapped_column()
    last_review_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_rating: Mapped[Rating] = mapped_column(enum_column(Rating))
    review_count: Mapped[int] = mapped_column()
    lapse_count: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ReviewLog(Base):
    __tablename__ = "review_log"
    __table_args__ = (
        CheckConstraint("mastery_after BETWEEN 0 AND 100", name="mastery_range"),
        Index("ix_reviews_user_time", "user_id", "accepted_at", "event_key"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    event_key: Mapped[UUID] = mapped_column(primary_key=True)
    sense_id: Mapped[int] = mapped_column(
        ForeignKey("lexi.senses.id", ondelete="RESTRICT"), index=True
    )
    rating: Mapped[Rating] = mapped_column(enum_column(Rating))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    applied: Mapped[bool] = mapped_column()
    mastery_after: Mapped[int] = mapped_column()
    due_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
