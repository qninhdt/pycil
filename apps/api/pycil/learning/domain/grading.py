"""Adapters between Pycil's answer wire shape and Lexi's typed grading contract."""

from dataclasses import asdict

from shared.fsrs import GRADE_AGAIN, GRADE_GOOD

from pycil.ports.lexi import AnswerSubmission, PresentedQuestion, Reveal, TextResponse


def answer_submission(question: PresentedQuestion, answer: str) -> AnswerSubmission:
    """Preserve Pycil's string answer API while using Lexi's typed submission."""
    return AnswerSubmission(question_id=question.question_id, response=TextResponse(answer))


def reveal_payload(reveal: Reveal | None) -> dict | None:
    """Serialize a sanctioned post-grade reveal for the existing REST contract."""
    return None if reveal is None else asdict(reveal)


def fsrs_grade_for(applied_grade: str) -> int:
    """Session score decision -> FSRS binary grade. ``good``->Good(3), else Again(1)."""
    return GRADE_GOOD if applied_grade == "good" else GRADE_AGAIN
