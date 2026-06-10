"""Multiple-choice question plugin.

Pydantic schemas mirror what the LLM returns and what the API stores in
``questions.data`` JSONB. The plugin wires the registry contract: which Jinja
template to render, what variables to pass, how to sanitize LLM output, what to
hide pre-submit, and how to grade a selection.
"""
from __future__ import annotations

from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from shared.questions.plugin import CheckResult, QuestionPlugin
from shared.questions.registry import register
from shared.questions.sanitize import sanitize_list, sanitize_text

_OptionStr = Annotated[str, StringConstraints(min_length=1, max_length=200)]
_RationaleStr = Annotated[str, StringConstraints(min_length=1, max_length=400)]

#: Fields that reveal the answer and must be stripped from pre-submit fetches.
_ANSWER_FIELDS = ("correct_index", "explanation", "distractor_rationale")


class MCQData(BaseModel):
    """Persisted shape of an MCQ in ``questions.data`` JSONB."""

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
    """Inner ``answer`` object for ``POST /questions/{id}/check``."""

    selected_index: int = Field(ge=0, le=3)


@register
class MultipleChoiceQuestion(QuestionPlugin):
    type_id = "MULTIPLE_CHOICE"
    data_schema = MCQData
    requires_server_grading = False

    @classmethod
    def template_name(cls) -> str:
        return "mcq.md"

    @classmethod
    def prompt_inputs(
        cls, definition: dict[str, Any], difficulty: str, theme: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {
            "term_value": definition["term_value"],
            "part_of_speech": definition.get("part_of_speech"),
            "cefr_level": definition.get("cefr_level"),
            "canonical_meaning": definition.get("canonical_meaning"),
            "paraphrase_sample": definition.get("paraphrase_sample"),
            "example_sample": definition.get("example_sample"),
            "difficulty": difficulty,
            "theme_flavor": (theme or {}).get("prompt_flavor"),
        }

    @classmethod
    def sanitize(cls, output: MCQData) -> dict[str, Any]:
        return {
            "stem": sanitize_text(output.stem),
            "options": sanitize_list(output.options),
            "correct_index": output.correct_index,
            "explanation": sanitize_text(output.explanation),
            "distractor_rationale": sanitize_list(output.distractor_rationale),
        }

    @classmethod
    def public_projection(cls, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            return data
        return {k: v for k, v in data.items() if k not in _ANSWER_FIELDS}

    @classmethod
    def check_answer(
        cls, data: dict[str, Any], answer: dict[str, Any]
    ) -> CheckResult:
        selected: Any
        if isinstance(answer, dict):
            selected = answer.get("selected_index")
        else:
            selected = answer
        if not isinstance(selected, int) or isinstance(selected, bool):
            return CheckResult(
                correct=False, score=0.0, feedback="invalid_selected_index"
            )
        correct_index = data.get("correct_index")
        correct = selected == correct_index
        rationale = data.get("distractor_rationale")
        return CheckResult(
            correct=correct,
            score=1.0 if correct else 0.0,
            feedback=data.get("explanation"),
            reveal={
                "correct_index": correct_index
                if isinstance(correct_index, int)
                else 0,
                # Post-submit only — public_projection strips these from the
                # pre-submit fetch, so disclosing them here is not a leak.
                "explanation": data.get("explanation"),
                "distractor_rationale": rationale
                if isinstance(rationale, list)
                else [],
            },
        )
