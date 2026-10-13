from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pycil.infrastructure.database import Base, enum_column
from pycil.study.enums import QuestionArtifactType


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
        ForeignKey("senses.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    stability: Mapped[float] = mapped_column()
    difficulty: Mapped[float] = mapped_column()
    last_exposure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    elo: Mapped[float] = mapped_column()
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
    result: Mapped[dict[str, object]] = mapped_column(JSONB)


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


class QuestionArtifact(Base):
    __tablename__ = "question_artifacts"
    __table_args__ = (
        CheckConstraint("position >= 0 AND type_position >= 0", name="positions"),
        Index("ix_question_artifacts_scope", "sense_id", "theme_id", "position"),
        Index(
            "ix_question_artifacts_type_scope",
            "sense_id",
            "theme_id",
            "artifact_type",
            "type_position",
        ),
        Index("ix_question_artifacts_list_scope", "sense_id", "theme_id", "id"),
        Index(
            "ix_question_artifacts_type_list_scope", "sense_id", "theme_id", "artifact_type", "id"
        ),
        Index(
            "uq_artifact_payload",
            "sense_id",
            text("COALESCE(theme_id, 0)"),
            "artifact_type",
            "payload_hash",
            unique=True,
        ),
        Index(
            "uq_singleton_artifact",
            "sense_id",
            text("COALESCE(theme_id, 0)"),
            "artifact_type",
            unique=True,
            postgresql_where=text("artifact_type IN ('word_definition','word_to_usage')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sense_id: Mapped[int] = mapped_column(ForeignKey("senses.id", ondelete="CASCADE"))
    theme_id: Mapped[int | None] = mapped_column(
        ForeignKey("themes.id", ondelete="CASCADE"), index=True
    )
    artifact_type: Mapped[QuestionArtifactType] = mapped_column(enum_column(QuestionArtifactType))
    payload: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(server_default=text("0"))
    type_position: Mapped[int] = mapped_column(server_default=text("0"))
