"""Fill-in-blank question.

LLM picks one example sentence and replaces the headword with `___`.
User types the missing word; grading uses stricter normalization than
Write (single-word answer expected).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from shared.questions.base import BaseQuestion, CheckResult, QuestionType
from shared.questions.normalize import normalize_answer


class FillData(BaseModel):
    """Persisted shape of a Fill question in `questions.data` JSONB."""

    prompt: str = Field(min_length=4, max_length=400)
    expected_answer: str = Field(min_length=1, max_length=80)
    alt_answers: list[str] = Field(default_factory=list, max_length=5)
    sentence_id: int | None = None
    explanation: str = Field(default="", max_length=400)


class FillAnswerInput(BaseModel):
    user_answer: str = Field(max_length=80)


class FillInBlankQuestion(BaseQuestion):
    """Cloze-style single-word recall."""

    @classmethod
    def question_type(cls) -> QuestionType:
        return QuestionType.FILL_IN_BLANK

    @classmethod
    def template_name(cls) -> str:
        return "fill_in_blank.md"

    @classmethod
    def prompt_inputs(cls, *, term_value: str, definition_text: str | None = None) -> dict:
        return {
            "term_value": term_value,
            "definition_text": definition_text or "",
        }

    @classmethod
    def check_answer(cls, data: dict[str, Any], answer: dict[str, Any]) -> CheckResult:
        parsed = FillAnswerInput.model_validate(answer)
        ua = normalize_answer(parsed.user_answer)
        expected = normalize_answer(data.get("expected_answer") or "")
        alts = [normalize_answer(str(a)) for a in data.get("alt_answers", [])]
        if ua and (ua == expected or ua in alts):
            return CheckResult(correct=True, explanation=data.get("explanation", ""))
        return CheckResult(correct=False, explanation=data.get("explanation", ""))
