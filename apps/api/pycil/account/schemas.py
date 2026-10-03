"""The complete two-level preference contract, without a settings subsystem."""

from datetime import datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lexi_ai import ResponseFormat
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pycil.account.plans import Feature, Plan
from pycil.config import LearningPreferences, ProductConfig
from pycil.http import Problem


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LearningPatch(Strict):
    question_types: list[str] | None = None
    formats: list[str] | None = None
    questions_per_sense: Annotated[int, Field(strict=True, gt=0)] | None = None
    question_budget: Annotated[int, Field(strict=True, gt=0)] | None = None
    show_explanations: Annotated[bool, Field(strict=True)] | None = None

    @model_validator(mode="after")
    def no_explicit_null(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("learning preferences cannot be null")
        return self


class PreferencesPatch(Strict):
    locale: str | None = None
    timezone: str | None = None
    translation_language: str | None = None
    learning: LearningPatch | None = None

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


class Profile(Strict):
    id: UUID
    display_name: str | None
    plan: Plan
    settings: Preferences
    effective_learning: LearningPreferences | None
    learning_restriction: str | None


class Allowance(Strict):
    period_start: datetime
    period_end: datetime
    allowance_units: int
    used_units: int
    remaining_units: int


def preferences(saved: dict, config: ProductConfig) -> Preferences:
    defaults = config.account.defaults.model_dump()
    learning = config.learning.defaults.model_dump() | saved.get("learning", {})
    values = defaults | saved | {"learning": learning}
    result = Preferences.model_validate(values)
    if result.locale not in config.account.locales:
        raise ValueError("unsupported locale")
    if result.translation_language not in config.account.translation_languages:
        raise ValueError("unsupported translation language")
    try:
        ZoneInfo(result.timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("invalid IANA timezone") from exc
    config.learning.validate_preferences(result.learning)
    return result


def effective_learning(saved: dict, plan: Plan, config: ProductConfig) -> LearningPreferences:
    selected = preferences(saved, config).learning
    formats = selected.formats
    if Feature.ADVANCED_GRADING not in config.plans[plan].features:
        formats = [fmt for fmt in formats if fmt is ResponseFormat.SINGLE_CHOICE]
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
    merged = saved | changes
    if nested is not None:
        if "formats" in nested and Feature.ADVANCED_GRADING not in config.plans[plan].features:
            if any(fmt != ResponseFormat.SINGLE_CHOICE for fmt in nested["formats"]):
                raise Problem(403, "advanced_grading_not_available")
        merged["learning"] = saved.get("learning", {}) | nested
    try:
        preferences(merged, config)
    except ValueError as exc:
        raise Problem(422, "invalid_preferences") from exc
    return merged
