from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from lexi_ai import ResponseFormat
from lexi_ai.models import DefinitionGrade, Option, Question, Sense, SingleWordGrade, UsageGrade
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pycil.config import LearningPreferences
from pycil.study.models import Rating


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


PositiveID = Annotated[int, Field(strict=True, gt=0)]


class Prepare(Strict):
    node_id: UUID
    selection: Literal["NEW", "DUE", "AUTO"] = "AUTO"
    max_sense_count: Annotated[int, Field(strict=True, gt=0, le=100)] | None = None


class Grade(Strict):
    question_id: PositiveID
    format: ResponseFormat
    answer: str = Field(min_length=1)


class Review(Strict):
    sense_id: PositiveID
    rating: Rating


class ReviewBatch(Strict):
    results: list[Review] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique(self):
        if len({r.sense_id for r in self.results}) != len(self.results):
            raise ValueError("duplicate sense IDs")
        return self


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
    node_id: UUID
    selection: Literal["NEW", "DUE", "AUTO"]
    max_sense_count: int
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
    due_after: datetime


class BatchResult(Strict):
    accepted_at: datetime
    activity_day: date
    results: list[ReviewResult]


class Summary(Strict):
    node_id: UUID
    as_of: datetime
    total: int
    new: int | None
    studied: int | None
    due: int | None
    not_due: int | None
    last_studied_at: datetime | None
    coverage: float | None
    immediate_folders: int
    immediate_decks: int
    immediate_references: int
    reachable_decks: int


class SummaryBatch(Strict):
    node_ids: list[UUID] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.node_ids)) != len(self.node_ids):
            raise ValueError("duplicate node IDs")
        return self


class ActivityDay(Strict):
    day: date
    applied_events: int
    practice_events: int


class Activity(Strict):
    as_of: datetime
    timezone: str
    start_date: date
    end_date: date
    days: list[ActivityDay]
    applied_events: int
    practice_events: int
    current_streak: int
    longest_streak: int


class ScheduledDay(Strict):
    day: date
    count: int


class Schedule(Strict):
    node_id: UUID
    as_of: datetime
    timezone: str
    start_date: date
    end_date: date
    days: list[ScheduledDay]
