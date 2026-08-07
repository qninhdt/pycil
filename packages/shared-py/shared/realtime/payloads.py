"""Typed realtime event payload for the durable task snapshot.

A plain dataclass serialized to dict for the outbox payload. It is the single
definition of this wire shape, so the frontend sees one stable grading event.
"""

from dataclasses import dataclass


@dataclass
class GradingResult:
    response_id: str
    sense_id: int
    is_correct: bool
    grade_score: float
    grade_feedback: str | None = None
    mastery_before: int | None = None
    mastery_after: int | None = None
    render_format: str = "free_text"
    reveal: dict | None = None

    def to_dict(self) -> dict:
        return {
            "responseId": self.response_id,
            "senseId": self.sense_id,
            "isCorrect": self.is_correct,
            "gradeScore": self.grade_score,
            "gradeFeedback": self.grade_feedback,
            "masteryBefore": self.mastery_before,
            "masteryAfter": self.mastery_after,
            "renderFormat": self.render_format,
            "reveal": self.reveal,
        }
