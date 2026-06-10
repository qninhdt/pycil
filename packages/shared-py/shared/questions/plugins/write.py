"""Write (free-text recall) question plugin.

User types a definition/paraphrase for a term. ``requires_server_grading`` is
True: ``check_answer`` here is the sync fast path (exact/normalized match); the
async LLM-judge tier is dispatched by the grading branch (see the grade job).

Persisted shape and answer-field policy mirror the legacy module so generation
behavior is unchanged: ``prompt``/``explanation`` get full ``sanitize_text``;
``expected_answer``/``alt_answers`` get control-char-only ``sanitize_answer``
(URLs/HTML may legitimately be the correct answer).
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


class WriteData(BaseModel):
    """Persisted shape of a Write question in ``questions.data`` JSONB."""

    prompt: str = Field(min_length=4, max_length=400)
    expected_answer: str = Field(min_length=1, max_length=400)
    alt_answers: list[str] = Field(default_factory=list, max_length=5)
    explanation: str = Field(default="", max_length=400)


class WriteAnswerInput(BaseModel):
    """Inner ``answer`` object for the check payload."""

    user_answer: str = Field(max_length=1000)


@register
class WriteQuestion(QuestionPlugin):
    type_id = "WRITE"
    data_schema = WriteData
    requires_server_grading = True

    @classmethod
    def template_name(cls) -> str:
        return "write.md"

    @classmethod
    def prompt_inputs(
        cls, definition: dict[str, Any], difficulty: str, theme: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {
            "term_value": definition["term_value"],
            "definition_text": definition.get("canonical_meaning") or "",
            "difficulty": difficulty,
        }

    @classmethod
    def sanitize(cls, output: WriteData) -> dict[str, Any]:
        return {
            "prompt": sanitize_text(output.prompt),
            "expected_answer": sanitize_answer(output.expected_answer),
            "alt_answers": sanitize_answer_list(output.alt_answers),
            "explanation": sanitize_text(output.explanation),
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
        """Sync fast path: exact/normalized match. The async LLM-judge tier is
        dispatched separately when this returns incorrect (requires_server_grading)."""
        parsed = WriteAnswerInput.model_validate(answer)
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
