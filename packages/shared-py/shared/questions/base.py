"""BaseQuestion ABC.

All question types implement two class methods:
- `generate_prompt(definition, difficulty)` — builds the LLM prompt input
  payload. The worker renders the corresponding Jinja2 template.
- `check_answer(question_data, user_answer)` — validates the user's response
  against the persisted question payload. Returns (correct, explanation).

v1 ships only `MultipleChoiceQuestion`. The ABC is kept narrow so v0.2 plug-in
subclasses (Write, Fill) can land without refactoring callers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    WRITE = "WRITE"
    FILL_IN_BLANK = "FILL_IN_BLANK"


class CheckResult:
    __slots__ = ("correct", "explanation")

    def __init__(self, correct: bool, explanation: str | None = None) -> None:
        self.correct = correct
        self.explanation = explanation


class BaseQuestion(ABC):
    """Abstract contract every question subclass must satisfy."""

    type: QuestionType

    @classmethod
    @abstractmethod
    def template_name(cls) -> str:
        """Jinja2 template filename under apps/worker/prompts/."""

    @classmethod
    @abstractmethod
    def prompt_inputs(cls, definition: dict[str, Any], difficulty: str) -> dict[str, Any]:
        """Variables passed to the Jinja2 template render."""

    @classmethod
    @abstractmethod
    def check_answer(
        cls, question_data: dict[str, Any], user_answer: Any
    ) -> CheckResult:
        """Validate `user_answer` against the persisted `question_data`."""
