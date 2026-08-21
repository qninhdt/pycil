"""Task lifecycle vocabulary: the states a task and its outbox row can be in.

Plain enums with no ORM dependency, which is why they live in `domain/` rather
than beside the tables that store them. They were in `infra/models.py`, so a
consumer wanting only the vocabulary — the wire schemas, a status comparison — had
to import a module full of `SQLModel` tables to get it.

This module also re-exports the cross-service job contract (task kinds, job
names, typed dispatch payloads) from shared-py, so producers inside pycil have
one internal import site for it.

Both are terminal-state machines, and which states are terminal is the fact most
of the codebase actually needs.
"""

from enum import Enum

from shared.tasks.contract import (
    JOB_NAME_FOR_KIND,
    JOB_NAME_GRADE_ANSWER_V1,
    TASK_KIND_GRADING,
    TASK_KIND_QUESTION_SUPPLY,
    TASK_KIND_WORD,
    WORKER_HEARTBEAT_KEY,
    WORKER_HEARTBEAT_TTL_SECONDS,
    GradingDispatch,
    SupplyDispatch,
    WordDispatch,
)

__all__ = [
    "AsyncTaskStatus",
    "GradingDispatch",
    "JOB_NAME_FOR_KIND",
    "JOB_NAME_GRADE_ANSWER_V1",
    "OutboxStatus",
    "SupplyDispatch",
    "TASK_KIND_GRADING",
    "TASK_KIND_QUESTION_SUPPLY",
    "TASK_KIND_WORD",
    "WORKER_HEARTBEAT_KEY",
    "WORKER_HEARTBEAT_TTL_SECONDS",
    "WordDispatch",
]


class AsyncTaskStatus(str, Enum):
    """Where a task is in its lifecycle.

    `SUCCEEDED`, `FAILED` and `EXPIRED` are terminal: a task in one of them is
    never claimed again, and its interest window starts its grace countdown.
    `EXPIRED` specifically means the lease ran out with no worker reporting back —
    distinct from `FAILED`, which is a worker saying the work cannot be done.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class OutboxStatus(str, Enum):
    """Delivery state of one transactional-outbox row.

    `LEASED` is the crash-safety state: a publisher holds the row for a bounded
    window, so a process that dies mid-publish releases it back rather than
    stranding the event. `DEAD_LETTER` is where a row goes after the retry budget
    is spent — kept rather than deleted, because a lost event should be
    investigable.
    """

    PENDING = "pending"
    LEASED = "leased"
    DELIVERED = "delivered"
    DEAD_LETTER = "dead_letter"
