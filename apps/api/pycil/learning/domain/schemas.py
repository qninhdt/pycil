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


class LearningSettingsUpdate(BaseModel):
    """The learner's session shape.

    Per user, not per deck. Holding these on a deck meant the same person got a
    different session length depending on which deck they opened, and a folder
    session ignored them entirely because a folder has no settings row — so the
    values only applied about half the time.

    The bounds are duplicated as CHECK constraints on the table. The planner
    divides its work by both numbers, so a zero arriving from anywhere would build
    a session with nothing in it.
    """

    target_words_per_session: int = Field(alias="targetWordsPerSession", ge=1, le=100)
    max_questions_per_round: int = Field(alias="maxQuestionsPerRound", ge=1, le=100)

    model_config = {"populate_by_name": True}


class LearningSettingsRead(BaseModel):
    """Effective session shape: the learner's row, or the policy defaults.

    Never an empty object. A learner who has never opened Settings has no row, and
    reporting that as ``{}`` would make every client reimplement the defaults in
    order to show anything.
    """

    target_words_per_session: int = Field(serialization_alias="targetWordsPerSession")
    max_questions_per_round: int = Field(serialization_alias="maxQuestionsPerRound")


class SessionRead(BaseModel):
    session_id: str = Field(serialization_alias="sessionId")
    node_id: UUID = Field(serialization_alias="nodeId")
    admitted_count: int = Field(serialization_alias="admittedCount")
    expires_at: str = Field(serialization_alias="expiresAt")
    first_state: str = Field(serialization_alias="firstState")


class SessionSenseProgressRead(BaseModel):
    """Where one admitted sense stands. Live-session shape only."""

    sense_id: int = Field(serialization_alias="senseId")
    purpose: str
    passed: int
    required: int
    score: str
    exposed: bool
    awaiting_grade: bool = Field(serialization_alias="awaitingGrade")
    terminal: bool
    terminal_reason: str = Field(serialization_alias="terminalReason")


class SessionStateRead(BaseModel):
    """One session, live or finished.

    ``status`` discriminates: ``live`` is served from Redis and carries the round
    counters and per-sense progress; ``completed`` is served from the durable
    summary row and carries the recap counts only, because ``end_session`` deleted
    the live namespace. A client that reloads mid-session gets ``live``; one that
    reloads after finishing gets ``completed`` instead of a 404.
    """

    session_id: str = Field(serialization_alias="sessionId")
    status: Literal["live", "completed"]
    node_id: UUID | None = Field(default=None, serialization_alias="nodeId")
    # Live only.
    round_index: int | None = Field(default=None, serialization_alias="roundIndex")
    round_count: int | None = Field(default=None, serialization_alias="roundCount")
    max_per_round: int | None = Field(default=None, serialization_alias="maxPerRound")
    expires_at: str | None = Field(default=None, serialization_alias="expiresAt")
    senses: list[SessionSenseProgressRead] = Field(default_factory=list)
    # Both, sourced from Redis while live and from the summary row afterwards.
    senses_admitted: int = Field(default=0, serialization_alias="sensesAdmitted")
    senses_completed: int = Field(default=0, serialization_alias="sensesCompleted")
    senses_exhausted: int = Field(default=0, serialization_alias="sensesExhausted")
    answers_total: int = Field(default=0, serialization_alias="answersTotal")
    answers_correct: int = Field(default=0, serialization_alias="answersCorrect")
    rounds_used: int = Field(default=0, serialization_alias="roundsUsed")
    completed_at: str | None = Field(default=None, serialization_alias="completedAt")


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
    """Eligible work exists but supply is still warming.

    ``task_id`` is the durable supply task, and subscribing to ``async:{task_id}``
    is how the client learns that supply landed. That matters because the
    alternative is calling ``/next`` again, and ``/next`` mutates — it advances
    rounds, reserves deliveries and extends the exclusion set — so repeating it
    while waiting is the one thing worth removing here.

    Null when the request started no task: refused by the per-learner generation
    slot, or still inside its cooldown. There is nothing to subscribe to in that
    case, so the client falls back to asking again shortly. Null means "ask again",
    never "no supply is coming".
    """

    state: Literal["preparing"] = "preparing"
    task_id: UUID | None = Field(default=None, serialization_alias="taskId")


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
