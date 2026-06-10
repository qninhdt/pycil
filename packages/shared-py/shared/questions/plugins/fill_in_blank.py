"""Fill-in-blank (cloze) question plugin.

LLM replaces a headword in an example sentence with ``___``; user types the
missing word. Single-word recall — grading is pure/sync (rule-based), so
``requires_server_grading`` is False.

Answer-field policy mirrors the legacy module: ``prompt``/``explanation`` full
``sanitize_text``; ``expected_answer``/``alt_answers`` control-char-only.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from shared.questions.normalize import normalize_answer
from shared.questions.plugin import CheckResult, QuestionPlugin
from shared.questions.registry import register
from shared.questions.sanitize import (
    sanitize_answer,
    sanitize_answer_list,
    sanitize_text,
)

#: Fields revealing the answer; stripped from pre-submit fetches.
_ANSWER_FIELDS = ("expected_answer", "alt_answers", "explanation")


class FillData(BaseModel):
    """Persisted shape of a Fill question in ``questions.data`` JSONB."""

    prompt: str = Field(min_length=4, max_length=400)
    expected_answer: str = Field(min_length=1, max_length=80)
    alt_answers: list[str] = Field(default_factory=list, max_length=5)
    sentence_id: int | None = None
    explanation: str = Field(default="", max_length=400)


class FillAnswerInput(BaseModel):
    """Inner ``answer`` object for the check payload."""

    user_answer: str = Field(max_length=80)


@register
class FillInBlankQuestion(QuestionPlugin):
    type_id = "FILL_IN_BLANK"
    data_schema = FillData
    requires_server_grading = False

    @classmethod
    def template_name(cls) -> str:
        return "fill_in_blank.md"

    @classmethod
    def prompt_inputs(
        cls, definition: dict[str, Any], difficulty: str, theme: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {
            "term_value": definition["term_value"],
            "definition_text": definition.get("canonical_meaning") or "",
            "example_sample": definition.get("example_sample"),
            "difficulty": difficulty,
        }

    @classmethod
    def sanitize(cls, output: FillData) -> dict[str, Any]:
        data: dict[str, Any] = {
            "prompt": sanitize_text(output.prompt),
            "expected_answer": sanitize_answer(output.expected_answer),
            "alt_answers": sanitize_answer_list(output.alt_answers),
            "explanation": sanitize_text(output.explanation),
        }
        if output.sentence_id is not None:
            data["sentence_id"] = output.sentence_id
        return data

    @classmethod
    def public_projection(cls, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            return data
        return {k: v for k, v in data.items() if k not in _ANSWER_FIELDS}

    @classmethod
    def check_answer(
        cls, data: dict[str, Any], answer: dict[str, Any]
    ) -> CheckResult:
        parsed = FillAnswerInput.model_validate(answer)
        ua = normalize_answer(parsed.user_answer)
        expected = normalize_answer(str(data.get("expected_answer") or ""))
        alts = [normalize_answer(str(a)) for a in data.get("alt_answers", [])]
        correct = bool(ua) and (ua == expected or ua in alts)
        return CheckResult(
            correct=correct,
            score=1.0 if correct else 0.0,
            feedback=data.get("explanation", ""),
            reveal={"expected_answer": data.get("expected_answer", "")},
        )
