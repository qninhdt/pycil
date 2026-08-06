"""FSRS per-sense learner state — the one ORM table more than one domain reads.

`UserSenseStats` is the durable memory model for a `(user, sense)` pair: FSRS
stability and difficulty, the derived `mastery`, and the scheduling dates. It lived
in `learning/models.py`, which is where it is *written* — but `content` and
`hierarchy` both read it, and that single import was the entire remaining
`content <-> hierarchy <-> learning` cycle:

* `content` annotates a sense view with the caller's mastery (`content/router.py`,
  `content/service.py`)
* `hierarchy` aggregates over the caller's tracked senses (`hierarchy/reads.py`)

Neither is reaching into learning's internals; both want the same read-only fact
about a learner. So the table moves to a shared home rather than the readers being
made to route through learning's application layer for a `SELECT`.

Only the model moves. Every FSRS *decision* — scheduling, grading, mastery
recomputation — stays in `learning/`, which remains the only writer.

Nothing in this package may import a domain, so `policy` cannot become a place
where behaviour accumulates alongside the data.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import BigInteger, Column, DateTime, text
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
