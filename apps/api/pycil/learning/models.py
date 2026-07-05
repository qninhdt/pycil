"""Learning-state ORM models: FSRS per-sense stats, review log, responses.

All ``sense_id``/``question_id`` are opaque bigints into lexi-ai's DB (no FK).
FSRS memory state (stability/difficulty) lives on ``user_sense_stats``; ``mastery``
is the discrete 0-100 saturation of stability. No ELO, no mastery_level.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import BigInteger, Column, DateTime, Index, text
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)


class SenseStatus(str, Enum):
    # Member name == value so the native PG enum label matches the JSON value.
    new = "new"
    learning = "learning"
    review = "review"
    buried = "buried"


class UserSenseStats(SQLModel, table=True):
    __tablename__ = "user_sense_stats"

    user_id: UUID = Field(foreign_key="users.id", primary_key=True)
    # Opaque ref into lexi-ai's DB — no FK.
    sense_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    stability: float = Field(default=0.0)
    difficulty: float = Field(default=0.0)
    mastery: int = Field(default=0)  # 0-100, saturation of stability
    interval_days: float = Field(default=0.0)
    last_review_date: datetime | None = Field(default=None, sa_type=TZDateTime)
    next_review_date: datetime | None = Field(default=None, sa_type=TZDateTime)
    review_count: int = Field(default=0)
    lapse_count: int = Field(default=0)
    status: SenseStatus = Field(default=SenseStatus.new)
    buried_until: datetime | None = Field(default=None, sa_type=TZDateTime)
    created_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    updated_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )


class ReviewLog(SQLModel, table=True):
    __tablename__ = "review_log"
    # Plain table for MVP scale — add partitioning via additive migration at 100M+.
    __table_args__ = (Index("idx_review_log_user_time", "user_id", "reviewed_at"),)

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    user_id: UUID = Field(foreign_key="users.id")
    sense_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    node_id: UUID | None = Field(default=None, foreign_key="nodes.id")
    stability_before: float
    stability_after: float
    mastery_before: int
    mastery_after: int
    grade: int  # FSRS grade: 1 (Again) or 3 (Good)
    reviewed_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )


class GradeStatus(str, Enum):
    # Member name == value so the native PG enum label matches the JSON value.
    pending = "pending"
    graded = "graded"


class Response(SQLModel, table=True):
    __tablename__ = "responses"
    # Pending async (WRITE) grades are polled/refetched by the apply step.
    __table_args__ = (
        Index(
            "idx_responses_pending",
            "grade_status",
            postgresql_where=text("grade_status = 'pending'"),
        ),
    )

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    user_id: UUID = Field(foreign_key="users.id", index=True)
    sense_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    # Opaque lexi question id.
    question_id: str
    is_correct: bool | None = None
    grade_status: GradeStatus = Field(default=GradeStatus.graded)
    grade_score: float | None = None
    grade_feedback: str | None = None
    answered_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    graded_at: datetime | None = Field(default=None, sa_type=TZDateTime)
