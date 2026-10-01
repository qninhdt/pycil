"""Learning DTOs for the Pycil Learning Session architecture.

Includes models for LearningPlan, QuestionResult, SessionResult,
settings, dashboard, and grading.
"""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SessionStart(BaseModel):
    node_id: UUID = Field(alias="nodeId")

    model_config = {"populate_by_name": True}


class LearningSettingsUpdate(BaseModel):
    """The learner's session shape."""

    target_words_per_session: int = Field(alias="targetWordsPerSession", ge=1, le=100)
    max_questions_per_round: int = Field(alias="maxQuestionsPerRound", ge=1, le=100)

    model_config = {"populate_by_name": True}


class LearningSettingsRead(BaseModel):
    """Effective session shape: the learner's row, or the policy defaults."""

    target_words_per_session: int = Field(serialization_alias="targetWordsPerSession")
    max_questions_per_round: int = Field(serialization_alias="maxQuestionsPerRound")


class SessionStateRead(BaseModel):
    """One session status, active or completed."""

    session_id: str = Field(serialization_alias="sessionId")
    status: Literal["live", "completed"]
    node_id: UUID | None = Field(default=None, serialization_alias="nodeId")
    round_index: int | None = Field(default=None, serialization_alias="roundIndex")
    round_count: int | None = Field(default=None, serialization_alias="roundCount")
    max_per_round: int | None = Field(default=None, serialization_alias="maxPerRound")
    expires_at: str | None = Field(default=None, serialization_alias="expiresAt")
    senses_admitted: int = Field(default=0, serialization_alias="sensesAdmitted")
    senses_completed: int = Field(default=0, serialization_alias="sensesCompleted")
    answers_total: int = Field(default=0, serialization_alias="answersTotal")
    answers_correct: int = Field(default=0, serialization_alias="answersCorrect")
    rounds_used: int = Field(default=0, serialization_alias="roundsUsed")
    completed_at: str | None = Field(default=None, serialization_alias="completedAt")


class GradeResponse(BaseModel):
    """Projection of one durable response."""

    response_id: UUID | None = Field(default=None, serialization_alias="responseId")
    grade_status: Literal["graded", "ungraded"] = Field(serialization_alias="gradeStatus")
    sense_id: int = Field(serialization_alias="senseId")
    render_format: str = Field(serialization_alias="renderFormat")
    is_correct: bool | None = Field(default=None, serialization_alias="isCorrect")
    grade_score: float | None = Field(default=None, serialization_alias="gradeScore")
    grade_feedback: str | None = Field(default=None, serialization_alias="gradeFeedback")
    reveal: dict | None = Field(default=None)
    mastery_before: int | None = Field(default=None, serialization_alias="masteryBefore")
    mastery_after: int | None = Field(default=None, serialization_alias="masteryAfter")
    depth_before: int | None = Field(default=None, serialization_alias="depthBefore")
    depth_after: int | None = Field(default=None, serialization_alias="depthAfter")
    depth_stage_name: str | None = Field(default=None, serialization_alias="depthStageName")


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


# --- Core learning session architecture contracts ------------------------------


class LearningPlanItem(BaseModel):
    question_id: int = Field(alias="questionId")
    sense_id: int = Field(alias="senseId")
    purpose: Literal["due", "new"]
    requested_level: int = Field(alias="requestedLevel")
    served_level: int = Field(alias="servedLevel")
    grading_mode: Literal["client", "server"] = Field(alias="gradingMode")

    model_config = {"populate_by_name": True}


class LearningPlan(BaseModel):
    version: int = 1
    items: list[LearningPlanItem] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class QuestionResult(BaseModel):
    question_id: int = Field(alias="questionId")
    outcome: Literal["correct", "incorrect"]

    model_config = {"populate_by_name": True}

    @property
    def is_correct(self) -> bool:
        return self.outcome == "correct"


class CompleteSessionRequest(BaseModel):
    results: list[QuestionResult]

    model_config = {"populate_by_name": True}


class SessionSummaryStats(BaseModel):
    questions: int
    correct: int
    incorrect: int
    senses_reviewed: int = Field(alias="sensesReviewed")

    model_config = {"populate_by_name": True}


class SenseMasteryChange(BaseModel):
    sense_id: int = Field(alias="senseId")
    mastery_before: int = Field(alias="masteryBefore")
    mastery_after: int = Field(alias="masteryAfter")
    depth_before: int | None = Field(default=None, alias="depthBefore")
    depth_after: int | None = Field(default=None, alias="depthAfter")

    model_config = {"populate_by_name": True}


class SessionResult(BaseModel):
    session_id: str = Field(alias="sessionId")
    completed: bool = True
    summary: SessionSummaryStats
    changes: list[SenseMasteryChange] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class GradeAnswerRequest(BaseModel):
    question_id: int = Field(alias="questionId")
    answer: str = Field(min_length=1, max_length=10_000)

    model_config = {"populate_by_name": True}


class GradeAnswerResponse(BaseModel):
    outcome: Literal["correct", "incorrect"]
    score: float | None = None
    feedback: str | None = None
    reveal: dict | None = None


class QuestionOption(BaseModel):
    id: str
    text: str

    model_config = {"populate_by_name": True}


class QuestionGrading(BaseModel):
    mode: Literal["client", "server"]
    correct_option_id: str | None = Field(default=None, serialization_alias="correctOptionId")
    correct_index: int | None = Field(default=None, serialization_alias="correctIndex")
    correct_option: str | None = Field(default=None, serialization_alias="correctOption")
    answer_norm: str | None = Field(default=None, serialization_alias="answerNorm")
    accepted_forms: list[str] | None = Field(default=None, serialization_alias="acceptedForms")
    answer: Any = None

    model_config = {"populate_by_name": True}


class SessionQuestionRead(BaseModel):
    id: int
    sense_id: int = Field(serialization_alias="senseId")
    format: str
    prompt: str | None = None
    options: list[QuestionOption] | None = None
    payload: dict | None = None
    grading: QuestionGrading

    model_config = {"populate_by_name": True}


class SessionCreateResponse(BaseModel):
    session_id: str = Field(serialization_alias="sessionId")
    node_id: UUID = Field(serialization_alias="nodeId")
    admitted_count: int = Field(serialization_alias="admittedCount")
    expires_at: str = Field(serialization_alias="expiresAt")
    first_state: str = Field(default="ready", serialization_alias="firstState")
    plan: LearningPlan
    questions: list[SessionQuestionRead]

    model_config = {"populate_by_name": True}
