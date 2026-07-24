"""Learning DTOs — session/round/question/answer. Sense-based, opaque ids.

Ready questions are generic DTOs carrying an answer-free payload dict supplied
by Lexi. Exposure is delivered as a flashcard with ``interaction_mode='exposure'``
and is not answered.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SessionStart(BaseModel):
    node_id: UUID = Field(alias="nodeId")

    model_config = {"populate_by_name": True}


class SessionRead(BaseModel):
    session_id: str = Field(serialization_alias="sessionId")
    node_id: UUID = Field(serialization_alias="nodeId")
    admitted_count: int = Field(serialization_alias="admittedCount")
    expires_at: str = Field(serialization_alias="expiresAt")
    first_state: str = Field(serialization_alias="firstState")


# --- ready question DTO (discriminated union keyed by render_format) -----------


class ReadyQuestionBase(BaseModel):
    state: Literal["ready"] = "ready"
    question_id: int | None = Field(serialization_alias="questionId")
    sense_id: int = Field(serialization_alias="senseId")
    interaction_mode: str = Field(serialization_alias="interactionMode")
    requested_level: int = Field(serialization_alias="requestedLevel")
    served_level: int = Field(serialization_alias="servedLevel")
    is_fallback: bool = Field(serialization_alias="isFallback")


class FlashcardReady(ReadyQuestionBase):
    render_format: Literal["flashcard"] = Field(
        default="flashcard", serialization_alias="renderFormat"
    )
    payload: dict


class SingleChoiceReady(ReadyQuestionBase):
    render_format: Literal["single_choice"] = Field(
        default="single_choice", serialization_alias="renderFormat"
    )
    payload: dict


class TextSpanReady(ReadyQuestionBase):
    render_format: Literal["text_span"] = Field(
        default="text_span", serialization_alias="renderFormat"
    )
    payload: dict


class FreeTextReady(ReadyQuestionBase):
    render_format: Literal["free_text"] = Field(
        default="free_text", serialization_alias="renderFormat"
    )
    payload: dict


ReadyQuestion = Annotated[
    FlashcardReady | SingleChoiceReady | TextSpanReady | FreeTextReady,
    Field(discriminator="render_format"),
]


# --- round / lifecycle signals --------------------------------------------------


class NextQuestionBreak(BaseModel):
    """A round completed — the FE may offer a break, then poll ``/next`` again."""

    state: Literal["break"] = "break"
    round_index: int = Field(serialization_alias="roundIndex")


class NextQuestionPreparing(BaseModel):
    """Eligible work exists but supply is still warming — poll ``/next`` shortly."""

    state: Literal["preparing"] = "preparing"


class NextQuestionWaiting(BaseModel):
    """All work is terminal but a pending (llm) grade is still settling."""

    state: Literal["waiting"] = "waiting"


class NextQuestionExhausted(BaseModel):
    state: Literal["exhausted"] = "exhausted"


# --- answer / grade --------------------------------------------------------------


class AnswerRequest(BaseModel):
    # Client sends ONLY the question id + its answer — never a question payload.
    # The server re-fetches the authoritative question by id and grades that.
    session_id: str = Field(alias="sessionId")
    question_id: int = Field(alias="questionId")
    answer: str = Field(min_length=1, max_length=10_000)

    model_config = {"populate_by_name": True}


class GradeResponse(BaseModel):
    """Grade result: rule types graded in-request with reveal data, llm types pending."""

    response_id: UUID = Field(serialization_alias="responseId")
    grade_status: str = Field(serialization_alias="gradeStatus")
    sense_id: int = Field(serialization_alias="senseId")
    render_format: str = Field(serialization_alias="renderFormat")
    task_id: UUID | None = Field(default=None, serialization_alias="taskId")
    is_correct: bool | None = Field(default=None, serialization_alias="isCorrect")
    grade_score: float | None = Field(default=None, serialization_alias="gradeScore")
    grade_feedback: str | None = Field(default=None, serialization_alias="gradeFeedback")
    reveal: dict | None = Field(default=None)
    mastery_before: int | None = Field(default=None, serialization_alias="masteryBefore")
    mastery_after: int | None = Field(default=None, serialization_alias="masteryAfter")


class FSRSForecastDay(BaseModel):
    date: str
    due_count: int = Field(serialization_alias="dueCount")


class RecentSessionInfo(BaseModel):
    node_id: UUID = Field(serialization_alias="nodeId")
    deck_title: str = Field(serialization_alias="deckTitle")
    remaining_count: int = Field(serialization_alias="remainingCount")


class DashboardStatsRead(BaseModel):
    total_learned_words: int = Field(serialization_alias="totalLearnedWords")
    due_today_count: int = Field(serialization_alias="dueTodayCount")
    mastery_percentage: float = Field(serialization_alias="masteryPercentage")
    fsrs_forecast: list[FSRSForecastDay] = Field(serialization_alias="fsrsForecast")
    recent_session: RecentSessionInfo | None = Field(
        default=None, serialization_alias="recentSession"
    )
