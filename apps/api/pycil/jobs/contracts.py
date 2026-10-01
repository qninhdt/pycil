"""Content-job kinds and arguments shared by the HTTP producer and task handler."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# These kinds appear in the receipt API consumed by the web client.
TASK_KIND_WORD = "word"
TASK_KIND_QUESTION_SUPPLY = "question_supply"


@dataclass(frozen=True)
class WordDispatch:
    """Private arguments of a word-generation task."""

    query: str
    owner_id: str

    def to_dispatch(self) -> dict:
        return {"query": self.query, "owner_id": self.owner_id}

    @classmethod
    def from_dispatch(cls, dispatch: dict) -> WordDispatch:
        # Key access on purpose: a payload missing a field must raise here rather
        # than run a job that cannot complete.
        return cls(query=dispatch["query"], owner_id=dispatch["owner_id"])


@dataclass(frozen=True)
class SupplyDispatch:
    """Private arguments of a question-supply task.

    Each demand is a ``(sense_id, difficulty_level)`` pair. ``to_dispatch``
    normalizes tuples to lists for the background callback.
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
    def from_dispatch(cls, dispatch: dict) -> SupplyDispatch:
        return cls(
            owner_id=dispatch["owner_id"],
            session_id=dispatch["session_id"],
            round_index=dispatch["round_index"],
            demands=dispatch["demands"],
        )
