"""Adapters between Pycil's answer wire shape and Lexi's typed grading contract."""

from dataclasses import asdict

from pycil.learning.fsrs import GRADE_AGAIN, GRADE_GOOD
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


#: Render kinds graded by asking a rubric judge, rather than by comparing the
#: answer against a stored key. Only free text needs the provider; every other
#: render kind is decided locally and costs the learner nothing.
_RUBRIC_RENDER_FORMATS = frozenset({"free_text"})


def evaluation_mechanism(render_format: str) -> str:
    """Which mechanism decided this answer: ``deterministic`` or ``rubric_judge``.

    Cost follows the mechanism, not the difficulty level. A level-4 answer given
    through a deterministic render is graded locally and is free, while a level-3
    free-text answer reaches the rubric judge and costs one Credit — so a level
    number must never be read as a synonym for "an LLM was involved".
    """
    return "rubric_judge" if render_format in _RUBRIC_RENDER_FORMATS else "deterministic"

