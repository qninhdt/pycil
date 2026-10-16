from datetime import date, datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, model_validator

from pycil.study.config import LearningPreferences
from pycil.study.enums import (
    DefinitionAccuracy,
    DefinitionCoverage,
    LearningState,
    MeaningPreservation,
    QuestionType,
    ResponseFormat,
    Selection,
    TargetPlacement,
    UsageForm,
    UsageMeaning,
)
from pycil.utils.schemas import PositiveID, Strict
from pycil.vocabulary.schemas import Sense


class Prepare(Strict):
    node_id: UUID
    selection: Literal[Selection.NEW, Selection.DUE, Selection.AUTO] = Selection.AUTO
    max_sense_count: Annotated[int, Field(strict=True, ge=1, le=20)] | None = None
    questions_per_sense: Annotated[int, Field(strict=True, ge=1, le=3)] | None = None


class QuizDiagnostic(Strict):
    correct: StrictBool


class SingleWordDiagnostic(Strict):
    task_fit: StrictBool
    spelling_error: StrictBool
    sense_id: PositiveID | None


class DefinitionDiagnostic(Strict):
    sense_id: PositiveID | None
    accuracy: DefinitionAccuracy | None
    coverage: DefinitionCoverage | None

    @model_validator(mode="after")
    def consistent(self):
        if (self.sense_id is None) != (self.accuracy is None and self.coverage is None):
            raise ValueError("Definition diagnostics require a matched Sense")
        if self.sense_id is not None and (self.accuracy is None or self.coverage is None):
            raise ValueError("Matched definition needs accuracy and coverage")
        return self


class UsageDiagnostic(Strict):
    used: StrictBool
    meaning: UsageMeaning | None
    form: UsageForm | None
    construction: StrictBool | None
    collocation: StrictBool | None
    appropriacy: StrictBool | None

    @model_validator(mode="after")
    def consistent(self):
        fields = (self.meaning, self.form, self.construction, self.collocation, self.appropriacy)
        if (
            self.used
            and any(v is None for v in fields)
            or not self.used
            and any(v is not None for v in fields)
        ):
            raise ValueError("Usage diagnostics disagree with target presence")
        return self


class RewriteDiagnostic(UsageDiagnostic):
    meaning_preservation: MeaningPreservation | None

    @model_validator(mode="after")
    def preservation(self):
        if self.used == (self.meaning_preservation is None):
            raise ValueError("Rewrite diagnostics disagree with target presence")
        return self


Diagnostics = (
    QuizDiagnostic
    | SingleWordDiagnostic
    | DefinitionDiagnostic
    | RewriteDiagnostic
    | UsageDiagnostic
)


class QuestionReference(Strict):
    question_artifact_id: PositiveID
    question_type: QuestionType
    format: ResponseFormat


class Grade(QuestionReference):
    answer: str | None = Field(min_length=1)


class GradeResult(QuestionReference):
    diagnostics: Diagnostics

    @model_validator(mode="before")
    @classmethod
    def diagnostic_shape(cls, value: object) -> object:
        if isinstance(value, dict):
            raw: dict[str, object] = cast(dict[str, object], value)
            if {"diagnostics", "format", "question_type"} <= raw.keys():
                fmt = ResponseFormat(cast(str, raw["format"]))
                kind = QuestionType(cast(str, raw["question_type"]))
                schema = (
                    QuizDiagnostic
                    if fmt == ResponseFormat.SINGLE_CHOICE
                    else SingleWordDiagnostic
                    if fmt == ResponseFormat.SINGLE_WORD
                    else DefinitionDiagnostic
                    if kind == QuestionType.WORD_TO_DEFINITION
                    else RewriteDiagnostic
                    if kind == QuestionType.SENTENCE_REWRITE
                    else UsageDiagnostic
                )
                diagnostics_val = schema.model_validate(raw["diagnostics"])
                updated: dict[str, object] = dict(raw)
                updated["diagnostics"] = diagnostics_val
                return updated
            return raw
        return value


class Review(GradeResult):
    answered_at: AwareDatetime


class ReviewBatch(Strict):
    results: list[Review] = Field(min_length=1, max_length=60)


class Option(Strict):
    id: str
    content: str


class DialogueTurn(Strict):
    speaker: str
    text: str | None


class Question(Strict):
    question_artifact_id: PositiveID
    sense_id: PositiveID
    question_type: QuestionType
    content: str | list[DialogueTurn]
    correct: Option
    distractors: list[Option]
    target_placement: TargetPlacement | None = None


class PreparedQuestion(Strict):
    question: Question
    format: ResponseFormat
    level: int = Field(ge=1, le=5)
    options: list[Option]


class PreparedBundle(Strict):
    sense: Sense
    reason: Literal[LearningState.DUE, LearningState.NEW, LearningState.NOT_YET_DUE]
    questions: list[PreparedQuestion]


class Preparation(Strict):
    node_id: UUID
    selection: Literal[Selection.NEW, Selection.DUE, Selection.AUTO]
    max_sense_count: int
    actual_sense_count: int
    actual_question_count: int
    preferences: LearningPreferences
    bundles: list[PreparedBundle]


class ReviewResult(Strict):
    sense_id: int
    applied: bool
    elo: float
    level: int
    stability: float
    difficulty: float
    last_exposure_at: datetime
    due_after: datetime


class TrackedEvidence(Review):
    evaluated_sense_id: int
    recall: float | None
    performance: float | None
    opponent_elo: float
    policy_version: int


class BatchResult(Strict):
    accepted_at: datetime
    activity_day: date
    results: list[ReviewResult]
    evidence: list[TrackedEvidence]


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
