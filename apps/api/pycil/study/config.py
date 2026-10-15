from typing import Annotated, Self

from pydantic import Field, model_validator

from pycil.infrastructure.configuration import Policy, PositiveInt
from pycil.study.enums import ALLOWED_PAIRS, QuestionType, ResponseFormat


class LearningPreferences(Policy):
    question_types: list[QuestionType]
    formats: list[ResponseFormat]
    questions_per_sense: PositiveInt
    max_sense_count: PositiveInt

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        for values in (self.question_types, self.formats):
            if not values or len(set(values)) != len(values):
                raise ValueError("type/format selections must be nonempty and unique")
        return self


class LearningLimits(Policy):
    min_questions_per_sense: PositiveInt
    max_questions_per_sense: Annotated[int, Field(strict=True, ge=1, le=3)]
    max_questions_per_prepare: Annotated[int, Field(strict=True, ge=1, le=60)]
    max_sense_count: Annotated[int, Field(strict=True, ge=1, le=20)]
    max_answer_chars: PositiveInt
    max_review_batch: Annotated[int, Field(strict=True, ge=1, le=60)]
    max_summary_nodes: Annotated[int, Field(strict=True, ge=1, le=50)]
    max_activity_days: Annotated[int, Field(strict=True, ge=1, le=366)]
    max_schedule_days: Annotated[int, Field(strict=True, ge=1, le=30)]


class MasteryPolicy(Policy):
    initial_elo: float
    k_elo: Annotated[float, Field(gt=0)]
    horizon_hours: Annotated[float, Field(gt=0)]
    level_thresholds: list[float] = Field(min_length=4, max_length=4)
    opponent_elo: list[float] = Field(min_length=5, max_length=5)
    policy_version: PositiveInt

    @model_validator(mode="after")
    def ordered_levels(self) -> Self:
        if self.level_thresholds != sorted(set(self.level_thresholds)):
            raise ValueError("Mastery thresholds must increase")
        if self.opponent_elo != sorted(set(self.opponent_elo)):
            raise ValueError("Opponent Elo must increase")
        return self

    def level(self, elo: float) -> int:
        return 1 + sum(elo >= threshold for threshold in self.level_thresholds)


class FSRSPolicy(Policy):
    desired_retention: Annotated[float, Field(gt=0, lt=1)]
    max_interval_days: PositiveInt
    initial_stability: Annotated[float, Field(gt=0)]
    initial_difficulty: Annotated[float, Field(ge=1, le=10)]


class ArtifactPolicy(Policy):
    correct_count: Annotated[int, Field(strict=True, ge=1, le=20)]
    distractor_count: Annotated[int, Field(strict=True, ge=3, le=20)]


class GradingPolicy(Policy):
    decision_threshold: Annotated[float, Field(strict=True, ge=0, le=1)]


class LearningPolicy(Policy):
    artifacts: ArtifactPolicy
    grading: GradingPolicy
    defaults: LearningPreferences
    limits: LearningLimits
    pair_levels: dict[
        QuestionType, dict[ResponseFormat, Annotated[int, Field(strict=True, ge=1, le=5)]]
    ]
    mastery: MasteryPolicy
    fsrs: FSRSPolicy

    @model_validator(mode="after")
    def validate_policy(self):
        pairs = {(kind, fmt) for kind, formats in self.pair_levels.items() for fmt in formats}
        if not pairs or not pairs <= ALLOWED_PAIRS:
            raise ValueError("unknown or unsupported type/format policy")
        self.validate_preferences(self.defaults)
        return self

    def validate_limits(self, preferences: LearningPreferences):
        if preferences.max_sense_count > self.limits.max_sense_count:
            raise ValueError("maximum Sense count exceeded")
        k = preferences.questions_per_sense
        if not self.limits.min_questions_per_sense <= k <= self.limits.max_questions_per_sense:
            raise ValueError("questions_per_sense outside configured bounds")
        if preferences.max_sense_count * k > self.limits.max_questions_per_prepare:
            raise ValueError("maximum prepared questions exceeded")

    def validate_preferences(self, preferences: LearningPreferences):
        self.validate_limits(preferences)
        feasible = any(
            any(fmt in self.pair_levels.get(kind, {}) for fmt in preferences.formats)
            for kind in preferences.question_types
        )
        if not feasible:
            raise ValueError("no product-enabled question type/format pair")
