"""The complete two-level preference contract, without a settings subsystem."""

import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from pycil.account.plans import Plan
from pycil.assistant.config import AssistantPreferences
from pycil.study.config import LearningLimits, LearningPreferences
from pycil.study.enums import QuestionType, ResponseFormat
from pycil.utils.schemas import Strict


class LearningPatch(Strict):
    question_types: list[QuestionType] | None = None
    formats: list[ResponseFormat] | None = None
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
    def valid_display_name(cls, value: str | None) -> str:
        if value is None or not 1 <= len(value.strip()) <= 255:
            raise ValueError("display name must contain 1–255 characters")
        return value.strip()

    @field_validator("handle")
    @classmethod
    def valid_handle(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("handle cannot be cleared")
        if not value.isascii():
            raise ValueError("handle must be ASCII")
        cleaned = value.strip().lower()
        if re.fullmatch(r"[a-z][a-z0-9_]{2,29}", cleaned, flags=re.ASCII) is None:
            raise ValueError("invalid handle")
        return cleaned

    @field_validator("bio")
    @classmethod
    def valid_bio(cls, value: str | None) -> str | None:
        if value is not None:
            cleaned = value.strip()
            if len(cleaned) > 500:
                raise ValueError("bio too long")
            return cleaned
        return None


class Allowance(Strict):
    period_start: datetime
    period_end: datetime
    allowance_units: int
    used_units: int
    remaining_units: int
