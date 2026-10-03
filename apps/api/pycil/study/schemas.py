from datetime import date, datetime
from typing import Literal
from uuid import UUID

from lexi_ai import CEFRLevel, ResponseFormat
from lexi_ai.models import DefinitionGrade, Option, Question, Sense, SingleWordGrade, UsageGrade
from pydantic import BaseModel, ConfigDict, Field

from pycil.config import LearningPreferences
from pycil.study.models import Rating


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Prepare(Strict):
    node_id: UUID


class Grade(Strict):
    question_id: int = Field(gt=0)
    format: ResponseFormat
    answer: str = Field(min_length=1)


class Review(Strict):
    sense_id: int = Field(gt=0)
    rating: Rating


class PreparedQuestion(Strict):
    question: Question
    format: ResponseFormat
    level: int = Field(ge=1, le=4)
    options: list[Option]


class PreparedBundle(Strict):
    sense: Sense
    reason: Literal["DUE", "NEW", "NOT_YET_DUE"]
    questions: list[PreparedQuestion]


class Preparation(Strict):
    requested_sense_count: int
    actual_sense_count: int
    actual_question_count: int
    preferences: LearningPreferences
    bundles: list[PreparedBundle]


GradeResult = SingleWordGrade | DefinitionGrade | UsageGrade


class ReviewResult(Strict):
    sense_id: int
    rating: Rating
    applied: bool
    accepted_at: datetime
    mastery_after: int
    due_after: datetime


class ReviewEvent(ReviewResult):
    user_id: UUID
    event_key: UUID


class History(Strict):
    events: list[ReviewEvent]
    next_after: UUID | None
    applied_count: int


class ProgressSummary(Strict):
    total: int
    learned: int
    due: int


class Activity(Strict):
    day: date
    applied_reviews: int
    practice_events: int


class Forecast(Strict):
    day: date
    count: int


class WeakSense(Strict):
    sense_id: int
    mastery: int


class CEFRDistribution(Strict):
    cefr_level: CEFRLevel | None
    count: int


class Progress(Strict):
    summary: ProgressSummary
    activity: list[Activity]
    forecast: list[Forecast]
    weakest_senses: list[WeakSense]
    cefr_distribution: list[CEFRDistribution]
