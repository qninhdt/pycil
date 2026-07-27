"""Learning-state ORM models: FSRS per-sense stats, review log, responses.

All ``sense_id``/``question_id`` are opaque bigints into lexi-ai's DB (no FK).
FSRS memory state (stability/difficulty) lives on ``user_sense_stats``; ``mastery``
is the discrete 0-100 saturation of stability.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import BigInteger, Column, DateTime, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)


class SenseStatus(str, Enum):
    # Member name == value so the native PG enum label matches the JSON value.
    # Two durable states: a sense is either untouched (``new``) or under FSRS
    # scheduling (``scheduled``).  The transient ``acquiring`` phase lives only in
    # Redis session state and is never persisted here.
    new = "new"
    scheduled = "scheduled"


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
    __table_args__ = (
        Index("idx_review_log_user_time", "user_id", "reviewed_at"),
        Index("idx_review_log_user_sense_time", "user_id", "sense_id", "reviewed_at"),
    )

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
    expired = "expired"


class Response(SQLModel, table=True):
    __tablename__ = "responses"
    # Pending async (WRITE) grades are polled/refetched by the apply step.
    __table_args__ = (
        Index(
            "idx_responses_pending",
            "grade_status",
            postgresql_where=text("grade_status = 'pending'"),
        ),
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
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    user_id: UUID = Field(foreign_key="users.id", index=True)
    session_id: str | None = Field(default=None, index=True, max_length=64)
    # Original learner input exists only until async rubric grading completes.
    raw_answer: str | None = Field(default=None, max_length=10_000)
    idempotency_key: str | None = Field(default=None, max_length=128)
    sense_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    # Opaque lexi question id (int end-to-end; None ids are ephemeral and rejected
    # before persistence).
    question_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    # Difficulty levels captured at delivery so an async settle can recompute
    # ``is_fallback = served_level < requested_level`` after Redis state expires.
    requested_level: int | None = None
    served_level: int | None = None
    is_correct: bool | None = None
    grade_status: GradeStatus = Field(default=GradeStatus.graded)
    grade_score: float | None = None
    grade_feedback: str | None = None
    # Persist the exact terminal projection so a worker crash can replay it.
    render_format: str | None = Field(default=None, max_length=32)
    reveal: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    # Persist FSRS snapshots for the task-delivery projection and audit trail.
    mastery_before: int | None = None
    mastery_after: int | None = None
    grading_lease_owner: str | None = Field(default=None, max_length=64)
    grading_lease_expires_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    grading_fence: int = Field(default=0)
    answered_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
    graded_at: datetime | None = Field(default=None, sa_type=TZDateTime)


class SessionSenseAttempt(SQLModel, table=True):
    """Durable first-attempt claim; many responses may still exist per sense."""

    __tablename__ = "session_sense_attempts"
    __table_args__ = (
        UniqueConstraint("user_id", "session_id", "sense_id", name="uq_session_sense_attempt"),
    )

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    user_id: UUID = Field(foreign_key="users.id", index=True)
    session_id: str = Field(max_length=64)
    sense_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    response_id: UUID | None = Field(default=None, foreign_key="responses.id")
    created_at: datetime | None = Field(
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
    __table_args__ = (
        UniqueConstraint("user_id", "session_id", name="uq_session_summary"),
    )

    id: UUID | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
        primary_key=True,
    )
    user_id: UUID = Field(foreign_key="users.id", index=True)
    session_id: str = Field(max_length=64)
    node_id: UUID | None = Field(default=None, foreign_key="nodes.id")
    # Admitted senses and how they ended.
    senses_admitted: int = Field(default=0)
    senses_completed: int = Field(default=0)
    senses_exhausted: int = Field(default=0)
    # Answered checkpoints, from the durable responses rows rather than Redis.
    answers_total: int = Field(default=0)
    answers_correct: int = Field(default=0)
    rounds_used: int = Field(default=0)
    started_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    completed_at: datetime | None = Field(
        default=None, sa_type=TZDateTime, sa_column_kwargs={"server_default": text("NOW()")}
    )
