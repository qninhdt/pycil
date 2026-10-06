from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pycil.database import Base, enum_column


class Rating(StrEnum):
    AGAIN = "AGAIN"
    HARD = "HARD"
    GOOD = "GOOD"
    EASY = "EASY"


class UserSense(Base):
    __tablename__ = "user_senses"
    __table_args__ = (
        CheckConstraint("stability > 0 AND difficulty > 0", name="positive_memory"),
        CheckConstraint("review_count > 0 AND lapse_count >= 0", name="valid_counts"),
        Index("ix_user_senses_user_due", "user_id", "due_at", "sense_id"),
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


class ReviewReceipt(Base):
    __tablename__ = "review_log"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    event_key: Mapped[UUID] = mapped_column(primary_key=True)
    request_hash: Mapped[str] = mapped_column(Text)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    activity_day: Mapped[date] = mapped_column()
    result: Mapped[dict] = mapped_column(JSONB)


class DailyActivity(Base):
    __tablename__ = "user_daily_activity"
    __table_args__ = (
        CheckConstraint("applied_events >= 0 AND practice_events >= 0", name="nonnegative_events"),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(primary_key=True)
    applied_events: Mapped[int] = mapped_column()
    practice_events: Mapped[int] = mapped_column()
