"""The disposable study-session document.

This holds *temporary* study state only: which senses were admitted, what has been
exposed, which delivery is outstanding, and how far through the rounds the learner
is. It deliberately does **not** hold FSRS stability or difficulty, next-review
dates, deck membership or account balance. Those are canonical and live in
PostgreSQL, written the moment an answer is graded — so a Redis loss can end a live
session but can never erase learning.

``stability``/``difficulty``/``due`` used to sit here as unused ``SessionItemDoc``
fields. They were never read or written, but their presence invited exactly the
mistake this design forbids: treating a disposable cache as the scheduler.
"""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SenseProgressDoc(BaseModel):
    sense_id: int
    exposed: bool = False
    last_round_used: int = -1
    current_qid: int | None = None
    current_kind: str = ""
    delivery_round: int | None = None
    delivery_id: UUID | None = None
    claim_token: str | None = None
    claim_expires_at: datetime | None = None
    requested_level: int = 1
    reask_pending: bool = False
    reask_level: int | None = None
    reask_failed_round: int | None = None
    reask_done: bool = False
    terminal: bool = False
    terminal_reason: str = ""
    failed_count: int = 0


class StudySessionDoc(BaseModel):
    session_id: str
    schema_version: int = 1
    owner_id: UUID
    node_id: UUID
    scope_generation: int = 1
    version: int = 1
    state: str = "ACTIVE"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    round_index: int = 0
    round_count: int = 0
    target_words: int
    max_per_round: int
    new_count: int = 0
    failed_count: int = 0
    items_served: int = 0
    prepare_attempts: int = 0
    prepare_retry_at: float = 0.0

    admitted: dict[int, str] = Field(default_factory=dict)
    progress: dict[int, SenseProgressDoc] = Field(default_factory=dict)
    graded: list[int] = Field(default_factory=list)
    excluded: dict[int, list[int]] = Field(default_factory=dict)
