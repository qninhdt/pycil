"""Typed realtime event payloads — shared by api + worker publishers.

Plain dataclasses serialized to dict for the Centrifugo publish body. Keep these
in sync on both sides so the frontend sees one stable event shape per channel.
"""

from dataclasses import asdict, dataclass


@dataclass
class JobUpdate:
    job_id: str
    status: str  # queued | running | done | error
    detail: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GradingResult:
    response_id: str
    sense_id: int
    is_correct: bool
    grade_score: float
    grade_feedback: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Notification:
    kind: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)
