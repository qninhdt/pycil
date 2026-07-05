"""Learning DTOs — session/question/answer. Sense-based, opaque ids."""

from uuid import UUID

from pydantic import BaseModel, Field


class SessionStart(BaseModel):
    node_id: UUID = Field(alias="nodeId")

    model_config = {"populate_by_name": True}


class SessionRead(BaseModel):
    session_id: str = Field(serialization_alias="sessionId")
    node_id: UUID = Field(serialization_alias="nodeId")
    queue_size: int = Field(serialization_alias="queueSize")


class NextQuestion(BaseModel):
    question_id: int = Field(serialization_alias="questionId")
    sense_id: int = Field(serialization_alias="senseId")
    recommended_type: str = Field(serialization_alias="recommendedType")
    payload: dict


class AnswerRequest(BaseModel):
    # Client sends ONLY the question id + its answer — never a question payload.
    # The server re-fetches the authoritative question by id and grades that.
    session_id: str = Field(alias="sessionId")
    question_id: int = Field(alias="questionId")
    answer: str

    model_config = {"populate_by_name": True}


class GradeResponse(BaseModel):
    """Mirrors lexi ``Score`` → pycil verdict fields."""

    sense_id: int = Field(serialization_alias="senseId")
    is_correct: bool = Field(serialization_alias="isCorrect")
    grade_score: float = Field(serialization_alias="gradeScore")
    grade_feedback: str | None = Field(default=None, serialization_alias="gradeFeedback")
    mastery_before: int = Field(serialization_alias="masteryBefore")
    mastery_after: int = Field(serialization_alias="masteryAfter")
