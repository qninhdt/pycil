"""The api↔worker content-job contract, stated once.

Job names, task kinds and the dispatch payload shapes both services exchange were
string literals repeated across the two codebases, held equal only by twin test
suites asserting each other's spelling. Every value here is the definition: the
API publishes by looking a kind up, and the worker registers the matching handler,
so a rename fails an import or a test instead of leaving a queued job unhandled.

Pure standard library. This module is imported by both services, so it must stay
dependency-free — importing taskiq here would drag the broker into the API's
request path.
"""

from collections.abc import Sequence
from dataclasses import dataclass

# Kinds are wire data: a published message names one, and the worker refuses a
# kind it has no handler for. Renaming one is a coordinated deploy, not an edit.
TASK_KIND_WORD = "word"
TASK_KIND_QUESTION_SUPPLY = "question_supply"

# The one registry mapping each kind to its worker handler name. The API
# publishes by lookup and the worker registers by the same names, so the two ends
# cannot disagree about which function serves which kind.
JOB_NAME_FOR_KIND = {
    TASK_KIND_WORD: "generate_word_task",
    TASK_KIND_QUESTION_SUPPLY: "prepare_questions_task",
}

# The Stream both services use, and the consumer group workers join. A second
# worker joins the same group rather than inventing its own, which is what stops
# a starting worker from taking work a live one is already running.
STREAM_NAME = "pycil:jobs"
CONSUMER_GROUP_NAME = "pycil_workers"

# Liveness signal the worker refreshes and the API readiness probe reads.
WORKER_HEARTBEAT_KEY = "worker:heartbeat"
WORKER_HEARTBEAT_TTL_SECONDS = 90

#: Bumped when a dispatch payload's shape changes incompatibly. A worker refuses a
#: version it does not know rather than guessing at the fields, so a half-rolled-out
#: deploy fails loudly instead of misreading a payload.
PAYLOAD_VERSION = 1


@dataclass(frozen=True)
class WordDispatch:
    """Private arguments of a word-generation task.

    ``to_dispatch`` is the only writer of the payload; ``from_dispatch`` is the
    only reader. The worker receives these values from the broker and reloads
    nothing, so the shape is the contract.
    """

    query: str
    owner_id: str

    def to_dispatch(self) -> dict:
        return {"query": self.query, "owner_id": self.owner_id}

    @classmethod
    def from_dispatch(cls, dispatch: dict) -> "WordDispatch":
        # Key access on purpose: a payload missing a field must raise here rather
        # than run a job that cannot complete.
        return cls(query=dispatch["query"], owner_id=dispatch["owner_id"])


@dataclass(frozen=True)
class SupplyDispatch:
    """Private arguments of a question-supply task.

    Each demand is a ``(sense_id, difficulty_level)`` pair — one item per
    ``(sense, level)``. Demands arrive as tuples from producers and as JSON lists
    out of the broker; ``to_dispatch`` normalizes both to lists so a round trip is
    stable.
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
