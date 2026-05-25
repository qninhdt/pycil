"""Multiple-choice question.

Pydantic schemas mirror what the LLM returns and what the API stores in
`questions.data` JSONB. `MultipleChoiceQuestion` wires the ABC contract:
which Jinja template to render, what variables to pass, and how to validate
the user's selection.
"""
from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from shared.questions.base import BaseQuestion, CheckResult, QuestionType


_OptionStr = Annotated[str, StringConstraints(min_length=1, max_length=200)]
_RationaleStr = Annotated[str, StringConstraints(min_length=1, max_length=400)]


class MCQData(BaseModel):
    """Persisted shape of an MCQ in `questions.data` JSONB."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    stem: str = Field(min_length=4, max_length=400)
    options: list[_OptionStr] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=4, max_length=400)
    distractor_rationale: list[_RationaleStr] = Field(min_length=3, max_length=3)

    @field_validator("options")
    @classmethod
    def _options_unique(cls, v: list[str]) -> list[str]:
        normalized = [opt.strip().lower() for opt in v]
        if len(set(normalized)) != 4:
            raise ValueError("mcq_options_must_be_unique")
        return v


class MCQAnswerInput(BaseModel):
    """Body shape for `POST /questions/{id}/check`."""

    selected_index: int = Field(ge=0, le=3)


class MultipleChoiceQuestion(BaseQuestion):
    type = QuestionType.MULTIPLE_CHOICE

    @classmethod
    def template_name(cls) -> str:
        return "mcq.md"

    @classmethod
    def prompt_inputs(
        cls, definition: dict[str, Any], difficulty: str
    ) -> dict[str, Any]:
        return {
            "term_value": definition["term_value"],
            "part_of_speech": definition.get("part_of_speech"),
            "cefr_level": definition.get("cefr_level"),
            "canonical_meaning": definition.get("canonical_meaning"),
            "paraphrase_sample": definition.get("paraphrase_sample"),
            "example_sample": definition.get("example_sample"),
            "difficulty": difficulty,
        }

    @classmethod
    def check_answer(
        cls, question_data: dict[str, Any], user_answer: Any
    ) -> CheckResult:
        if isinstance(user_answer, dict):
            selected = user_answer.get("selected_index")
        else:
            selected = user_answer
        if not isinstance(selected, int):
            return CheckResult(correct=False, explanation="invalid_selected_index")
        correct = selected == question_data.get("correct_index")
        return CheckResult(
            correct=correct, explanation=question_data.get("explanation")
        )
