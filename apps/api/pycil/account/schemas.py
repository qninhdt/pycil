"""The complete two-level preference contract, without a settings subsystem."""

import re
from datetime import datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lexi_ai import QuestionType, ResponseFormat
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pycil.account.plans import Feature, Plan
from pycil.config import AssistantPreferences, LearningLimits, LearningPreferences, ProductConfig
from pycil.http import Problem


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LearningPatch(Strict):
    question_types: list[str] | None = None
    formats: list[str] | None = None
    questions_per_sense: Annotated[int, Field(strict=True, gt=0)] | None = None
    max_sense_count: Annotated[int, Field(strict=True, gt=0)] | None = None

    @model_validator(mode="after")
    def no_explicit_null(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("learning preferences cannot be null")
        return self


class AssistantPatch(Strict):
    auto_approve: Annotated[bool, Field(strict=True)] | None = None

    @model_validator(mode="after")
    def no_explicit_null(self):
        if "auto_approve" in self.model_fields_set and self.auto_approve is None:
            raise ValueError("assistant preferences cannot be null")
        return self


class PreferencesPatch(Strict):
    locale: str | None = None
    timezone: str | None = None
    translation_language: str | None = None
    learning: LearningPatch | None = None
    assistant: AssistantPatch | None = None

    @model_validator(mode="after")
    def no_explicit_null(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("preferences cannot be null")
        return self


class Preferences(Strict):
    locale: str
    timezone: str
    translation_language: str
    learning: LearningPreferences
    assistant: AssistantPreferences


class LearningPair(Strict):
    question_type: QuestionType
    format: ResponseFormat
    level: Annotated[int, Field(ge=1, le=5)]


class LearningOptions(Strict):
    pairs: list[LearningPair]
    limits: LearningLimits
    advanced_grading: bool


class Profile(Strict):
    id: UUID
    display_name: str | None
    handle: str | None
    bio: str | None
    joined_at: datetime
    learning_options: LearningOptions
    plan: Plan
    settings: Preferences
    effective_learning: LearningPreferences | None
    learning_restriction: str | None
    library_node_id: UUID
    personal_node_id: UUID
    published_node_id: UUID


class PublicProfile(Strict):
    id: UUID
    display_name: str | None
    handle: str | None
    bio: str | None
    joined_at: datetime
    published_node_id: UUID


class ProfilePatch(Strict):
    display_name: str | None = None
    handle: str | None = None
    bio: str | None = None

    @field_validator("display_name")
    @classmethod
    def valid_display_name(cls, value):
        if value is None or not 1 <= len(value.strip()) <= 255:
            raise ValueError("display name must contain 1–255 characters")
        return value.strip()

    @field_validator("handle")
    @classmethod
    def valid_handle(cls, value):
        if value is None:
            raise ValueError("handle cannot be cleared")
        if not value.isascii():
            raise ValueError("handle must be ASCII")
        value = value.strip().lower()
        if re.fullmatch(r"[a-z][a-z0-9_]{2,29}", value, flags=re.ASCII) is None:
            raise ValueError("invalid handle")
        return value

    @field_validator("bio")
    @classmethod
    def valid_bio(cls, value):
        if value is not None:
            value = value.strip()
            if len(value) > 500:
                raise ValueError("bio too long")
        return value


class Allowance(Strict):
    period_start: datetime
    period_end: datetime
    allowance_units: int
    used_units: int
    remaining_units: int


def preferences(saved: dict, config: ProductConfig) -> Preferences:
    defaults = config.account.defaults.model_dump()
    learning = config.learning.defaults.model_dump() | saved.get("learning", {})
    assistant = defaults["assistant"] | saved.get("assistant", {})
    values = defaults | saved | {"learning": learning, "assistant": assistant}
    result = Preferences.model_validate(values)
    if result.locale not in config.account.locales:
        raise ValueError("unsupported locale")
    if result.translation_language not in config.account.translation_languages:
        raise ValueError("unsupported translation language")
    try:
        ZoneInfo(result.timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("invalid IANA timezone") from exc
    config.learning.validate_limits(result.learning)
    return result


def effective_learning(saved: dict, plan: Plan, config: ProductConfig) -> LearningPreferences:
    selected = preferences(saved, config).learning
    formats = selected.formats
    if Feature.ADVANCED_GRADING not in config.plans[plan].features:
        formats = [ResponseFormat.SINGLE_CHOICE]
    try:
        effective = LearningPreferences.model_validate(selected.model_dump() | {"formats": formats})
        config.learning.validate_preferences(effective)
    except ValueError as exc:
        raise Problem(422, "infeasible_learning_preferences") from exc
    return effective


def merge_preferences(
    saved: dict, patch: PreferencesPatch, plan: Plan, config: ProductConfig
) -> dict:
    changes = patch.model_dump(exclude_unset=True)
    nested = changes.pop("learning", None)
    assistant = changes.pop("assistant", None)
    merged = saved | changes
    if assistant is not None:
        merged["assistant"] = saved.get("assistant", {}) | assistant
    if nested is not None:
        if "formats" in nested and Feature.ADVANCED_GRADING not in config.plans[plan].features:
            if any(fmt != ResponseFormat.SINGLE_CHOICE for fmt in nested["formats"]):
                raise Problem(403, "advanced_grading_not_available")
        merged["learning"] = saved.get("learning", {}) | nested
    try:
        effective_learning(merged, plan, config)
    except (ValueError, Problem) as exc:
        raise Problem(422, "invalid_preferences") from exc
    return merged
