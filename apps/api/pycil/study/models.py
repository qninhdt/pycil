"""Learning-state ORM models: FSRS per-sense stats, review log, responses.

All ``sense_id``/``question_id`` are opaque bigints into lexi-ai's DB (no FK).
FSRS memory state (stability/difficulty) lives on ``user_sense_stats``; ``mastery``
is the discrete 0-100 saturation of stability.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)


class SenseStatus(StrEnum):
    new = "new"
    scheduled = "scheduled"


class UserSenseStats(SQLModel, table=True):
    __tablename__ = "user_sense_stats"

    user_id: UUID = Field(foreign_key="users.id", primary_key=True)
    sense_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    stability: float = Field(default=0.0)
    difficulty: float = Field(default=0.0)
    mastery: int = Field(default=0)
    interval_days: float = Field(default=0.0)
    last_review_date: datetime | None = Field(default=None, sa_type=TZDateTime)
    next_review_date: datetime | None = Field(default=None, sa_type=TZDateTime)
    review_count: int = Field(default=0)
    lapse_count: int = Field(default=0)
    status: SenseStatus = Field(default=SenseStatus.new)
    depth_level: int = Field(default=0)
    depth_streak: int = Field(default=0)
    created_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    updated_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )


class ReviewLog(SQLModel, table=True):
    __tablename__ = "review_log"
    # Plain table for MVP scale — add partitioning via additive migration at 100M+.
    __table_args__ = (
        Index("idx_review_log_user_time", "user_id", "reviewed_at"),
        Index("idx_review_log_user_sense_time", "user_id", "sense_id", "reviewed_at"),
    )

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True))
    user_id: UUID = Field(foreign_key="users.id")
    sense_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    # SET NULL, not the SQLModel default of no action: the FSRS history belongs to
    # the learner, so a deleted deck must release these rows rather than block its
    # own deletion.
    node_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(), ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True),
    )
    stability_before: float
    stability_after: float
    mastery_before: int
    mastery_after: int
    grade: int  # FSRS grade: 1 (Again) or 3 (Good)
    reviewed_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )


class Response(SQLModel, table=True):
    __tablename__ = "responses"
    __table_args__ = (
        UniqueConstraint("user_id", "session_id", "sense_id", name="uq_response_session_sense"),
        Index(
            "ix_responses_user_idempotency",
            "user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("uuidv7()")},
        primary_key=True,
    )
    user_id: UUID = Field(foreign_key="users.id", index=True)
    session_id: str | None = Field(default=None, index=True, max_length=64)
    idempotency_key: str | None = Field(default=None, max_length=128)
    sense_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    # Opaque lexi question id (int end-to-end; None ids are ephemeral and rejected
    # before persistence).
    question_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    requested_level: int | None = None
    served_level: int | None = None
    is_correct: bool = False
    # Every persisted response is terminal. ``ungraded`` re-asks never create rows.
    grade_status: str = Field(default="graded", max_length=16)
    grade_score: float | None = None
    grade_feedback: str | None = None
    render_format: str | None = Field(default=None, max_length=32)
    reveal: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    mastery_before: int | None = None
    mastery_after: int | None = None
    depth_before: int | None = None
    depth_after: int | None = None
    answered_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    graded_at: datetime | None = Field(default=None, sa_type=TZDateTime)


class UserLearningSettings(SQLModel, table=True):
    """How this learner's sessions are shaped.

    One row per learner, or none. An absent row means the policy defaults, so
    signing up writes nothing and a learner who never opens Settings stores
    nothing.

    Per user rather than per deck because session shape describes the person, not
    the material: the same learner wanting shorter sessions wants them everywhere.
    The previous per-deck JSONB also had no readable listing — a client showing
    "your settings" had to walk the whole node tree to discover every deck first.
    """

    __tablename__ = "user_learning_settings"

    user_id: UUID = Field(foreign_key="users.id", primary_key=True)
    target_words_per_session: int
    max_questions_per_round: int
    created_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    updated_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )


class SessionSummary(SQLModel, table=True):
    """Presentation-only recap of a finished session.

    Redis holds a session's live state and ``end_session`` deletes that namespace
    the moment the session completes, so without this row any reload during or
    after finishing a session returned 404 and the recap was lost.

    Deliberately NOT a second copy of scheduling state. FSRS effects stay
    authoritative in ``review_log`` and ``user_sense_stats``; these are counts,
    which cannot drift from anything because nothing reads them back into the
    domain.
    """

    __tablename__ = "session_summaries"
    __table_args__ = (UniqueConstraint("user_id", "session_id", name="uq_session_summary"),)

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("uuidv7()")},
        primary_key=True,
    )
    user_id: UUID = Field(foreign_key="users.id", index=True)
    session_id: str = Field(max_length=64)
    node_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(), ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True),
    )
    # Admitted senses and how they ended.
    senses_admitted: int = Field(default=0)
    senses_completed: int = Field(default=0)
    # Answered assessments, from durable responses rather than Redis.
    answers_total: int = Field(default=0)
    answers_correct: int = Field(default=0)
    rounds_used: int = Field(default=0)
    started_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    completed_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )


class StudySession(SQLModel, table=True):
    """Durable study session row.

    Holds the immutable LearningPlan snapshot and the completion SessionResult.
    Does not track live navigation, rounds, or intermediate progress.
    """

    __tablename__ = "study_session"

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("uuidv7()")},
        primary_key=True,
    )
    user_id: UUID = Field(foreign_key="users.id", index=True)
    node_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid(), ForeignKey("nodes.id", ondelete="SET NULL"), index=True, nullable=True
        ),
    )
    status: str = Field(default="active", max_length=16)  # "active" | "completed"
    created_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    completed_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    expires_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    plan: dict = Field(sa_column=Column(JSONB, nullable=False))
    result_summary: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
