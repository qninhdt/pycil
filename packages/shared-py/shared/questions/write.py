"""Write (free-text) question.

User types a definition or paraphrase for a term. Grading uses tiered
match in `pycil_core.services.answer_grading_service`: exact → normalize
→ Levenshtein ≤2 → LLM judge.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from shared.questions.base import BaseQuestion, CheckResult, QuestionType
from shared.questions.normalize import normalize_answer


class WriteData(BaseModel):
    """Persisted shape of a Write question in `questions.data` JSONB."""

    prompt: str = Field(min_length=4, max_length=400)
    expected_answer: str = Field(min_length=1, max_length=400)
    alt_answers: list[str] = Field(default_factory=list, max_length=5)
    explanation: str = Field(default="", max_length=400)


class WriteAnswerInput(BaseModel):
    user_answer: str = Field(max_length=1000)


class WriteQuestion(BaseQuestion):
    """Free-text recall question."""

    @classmethod
    def question_type(cls) -> QuestionType:
        return QuestionType.WRITE

    @classmethod
    def template_name(cls) -> str:
        return "write.md"

    @classmethod
    def prompt_inputs(cls, *, term_value: str, definition_text: str | None = None) -> dict:
        return {
            "term_value": term_value,
            "definition_text": definition_text or "",
        }

    @classmethod
    def check_answer(cls, data: dict[str, Any], answer: dict[str, Any]) -> CheckResult:
        """Stub equality check; real grading happens server-side via answer_grading_service."""
        parsed = WriteAnswerInput.model_validate(answer)
        ua = normalize_answer(parsed.user_answer)
        expected = normalize_answer(data.get("expected_answer") or "")
        alts = [normalize_answer(str(a)) for a in data.get("alt_answers", [])]
        if ua and (ua == expected or ua in alts):
            return CheckResult(correct=True, explanation=data.get("explanation", ""))
        return CheckResult(correct=False, explanation=data.get("explanation", ""))
