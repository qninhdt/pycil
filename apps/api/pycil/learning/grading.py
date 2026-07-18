"""Grade-verdict mapping. pycil does NO grading — the verdict comes entirely from
lexi-ai's ``Score`` (rule-based for mcq/cloze, LLM-judge for use_in_sentence).

This module only translates a lexi ``Score`` into (a) the FSRS binary grade and
(b) pycil's ``GradeResponse`` fields. No thresholds, no inline scoring.
"""

from shared.fsrs import GRADE_AGAIN, GRADE_GOOD

from pycil.content.lexi_types import Score
from pycil.learning.models import GradeStatus


def fsrs_grade(score: Score) -> int:
    """lexi verdict → FSRS binary grade. correct→Good(3), wrong→Again(1)."""
    return GRADE_GOOD if score.correct else GRADE_AGAIN


def grade_status_for(score: Score) -> GradeStatus:
    """A resolved lexi Score is always a completed verdict → graded."""
    return GradeStatus.graded
