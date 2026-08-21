"""The api↔worker async-job contract, stated once.

Job names, task kinds, dispatch payload shapes, and the runtime Redis keys both
services touch were string literals repeated across the two codebases, held
equal only by twin test suites asserting each other's spelling. Every value
here is the definition: producers enqueue by lookup, the worker asserts at
import time that its registrations cover the registry, and the reconciler
parses stored rows back through the same typed shapes they were written from —
so a rename or arity change fails an import or a unit test instead of leaving
queued jobs silently unhandled.

Pure standard library. This package is imported by both services and must stay
dependency-free.
"""

from collections.abc import Sequence
from dataclasses import dataclass

# Kinds are stored on durable `async_tasks.kind` rows and switched on by the
# re-enqueue reconciler, so they are wire data: renaming one is a migration,
# not an edit.
TASK_KIND_WORD = "word"
TASK_KIND_GRADING = "grading"
TASK_KIND_QUESTION_SUPPLY = "question_supply"

# Registry Pattern: this mapping is the single owner of which arq handler
# serves each task kind. Producers and the reconciler enqueue by lookup, and
# worker startup fails if its registrations do not cover every value.
JOB_NAME_FOR_KIND = {
    TASK_KIND_WORD: "generate_word_task",
    TASK_KIND_GRADING: "grade_answer_task",
    TASK_KIND_QUESTION_SUPPLY: "prepare_questions_task",
}

# Second grading entry point: the pending-grade reconciler re-enqueues by
# response id alone — its trigger row can predate the durable task — so it
# targets this handler rather than the task-backed one above.
JOB_NAME_GRADE_ANSWER_V1 = "grade_answer_v1"

# Liveness signal the worker refreshes and the API readiness probe reads.
WORKER_HEARTBEAT_KEY = "worker:heartbeat"
WORKER_HEARTBEAT_TTL_SECONDS = 90


@dataclass(frozen=True)
class WordDispatch:
    """Private arguments of a word-generation task.

    ``to_dispatch`` is the only writer of the stored payload and ``job_args``
    the only writer of the enqueue argument order, so reshaping either is one
    edit here rather than a hunt across producers, the reconciler, and the
    handler signature.
    """

    query: str
    owner_id: str

    def to_dispatch(self) -> dict:
        return {"query": self.query, "owner_id": self.owner_id}

    @classmethod
    def from_dispatch(cls, dispatch: dict) -> "WordDispatch":
        # Key access on purpose: a stored row missing a field must raise here,
        # not re-enqueue a job that cannot run to completion.
        return cls(query=dispatch["query"], owner_id=dispatch["owner_id"])

    def job_args(self) -> tuple[str, str]:
        """Handler arguments after the task id, in registration order."""
        return (self.query, self.owner_id)


@dataclass(frozen=True)
class GradingDispatch:
    """Private arguments of an answer-grading task."""

    owner_id: str
    response_id: str

    def to_dispatch(self) -> dict:
        return {"owner_id": self.owner_id, "response_id": self.response_id}

    @classmethod
    def from_dispatch(cls, dispatch: dict) -> "GradingDispatch":
        return cls(owner_id=dispatch["owner_id"], response_id=dispatch["response_id"])

    def job_args(self) -> tuple[str, str]:
        return (self.owner_id, self.response_id)


@dataclass(frozen=True)
class SupplyDispatch:
    """Private arguments of a question-supply task.

    ``session_id`` and ``round_index`` identify the work (they are also baked
    into the work key) but are not handler arguments — the job needs only the
    owner and the outstanding demands — so ``job_args`` projects them away
    while ``to_dispatch`` keeps them in storage for the reconciler's records.

    Demands arrive as tuples from producers and as JSON lists out of the
    stored row; ``to_dispatch`` normalizes both to lists, and ``job_args``
    forwards whatever the instance holds verbatim.
    """

    owner_id: str
    session_id: str
    round_index: int
    demands: Sequence[Sequence[int]]

    def to_dispatch(self) -> dict:
        return {
            "owner_id": self.owner_id,
            "session_id": self.session_id,
            "round_index": self.round_index,
            "demands": [list(demand) for demand in self.demands],
        }

    @classmethod
    def from_dispatch(cls, dispatch: dict) -> "SupplyDispatch":
        return cls(
            owner_id=dispatch["owner_id"],
            session_id=dispatch["session_id"],
            round_index=dispatch["round_index"],
            demands=dispatch["demands"],
        )

    def job_args(self) -> tuple[str, Sequence[Sequence[int]]]:
        return (self.owner_id, self.demands)
