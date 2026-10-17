"""Typed data structures and dictionaries for the study domain."""

from datetime import date, datetime
from typing import Literal, TypedDict
from uuid import UUID

from pycil.study.enums import LearningState
from pycil.study.schemas import LearningPreferences, PreparedQuestion
from pycil.vocabulary.schemas import Sense


class ThemeContext(TypedDict):
    id: int
    voice: str | None
    diction: str | None


class CompletionPointDict(TypedDict):
    turn_index: int
    distractors: list[str]


class ScopeSummaryRow(TypedDict):
    total: int
    studied: int
    due: int
    last_studied_at: datetime | None


class SummaryDict(TypedDict):
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


class ActivityDayDict(TypedDict):
    day: date
    applied_events: int
    practice_events: int


class ActivityDict(TypedDict):
    as_of: datetime
    active_days: int
    applied_events: int
    practice_events: int
    days: list[ActivityDayDict]


class ScheduledDayDict(TypedDict):
    day: date
    count: int


class ScheduleDict(TypedDict):
    as_of: datetime
    days: list[ScheduledDayDict]


class PreparationBundleDict(TypedDict):
    sense: Sense
    reason: LearningState | str
    questions: list[PreparedQuestion]


class PreparationDict(TypedDict):
    node_id: UUID
    selection: str
    max_sense_count: int
    actual_sense_count: int
    actual_question_count: int
    preferences: LearningPreferences
    bundles: list[PreparationBundleDict]


class UserSenseState(TypedDict, total=False):
    user_id: UUID
    sense_id: int
    elo: float
    stability: float
    difficulty: float
    last_exposure_at: datetime
    due_at: datetime
    review_count: int
    lapse_count: int
    created_at: datetime
    updated_at: datetime


class BatchResultDict(TypedDict):
    accepted: bool
    results: list[dict[str, object]]
    activity_day: date


class LearningPreviewDict(TypedDict):
    state: Literal[LearningState.NEW, LearningState.DUE, LearningState.NOT_YET_DUE]
    due_at: datetime | None
    elo: float | None
    level: int | None
    last_reviewed_at: datetime | None
