from datetime import UTC, datetime, timedelta

import pytest

from pycil.study.evidence import evidence, update_elo
from pycil.study.schemas import GradeResult


def grade(kind, fmt, diagnostics):
    return GradeResult(
        question_artifact_id=1, question_type=kind, format=fmt, diagnostics=diagnostics
    )


@pytest.mark.parametrize(
    "kind",
    [
        "DEFINITION_TO_WORD",
        "WORD_TO_DEFINITION",
        "CONTEXT_TO_WORD",
        "CLOZE_TO_WORD",
        "MEANING_IN_CONTEXT",
        "DIALOGUE_COMPLETION",
        "SENTENCE_REWRITE",
    ],
)
@pytest.mark.parametrize("correct", [False, True])
def test_quiz_evidence_is_binary(kind, correct):
    assert evidence(grade(kind, "SINGLE_CHOICE", {"correct": correct}), 1) == (
        1,
        float(correct),
        float(correct),
    )


def test_usage_quiz_has_performance_without_recall():
    assert evidence(grade("WORD_TO_USAGE", "SINGLE_CHOICE", {"correct": True}), 1) == (1, None, 1)


def test_single_word_and_definition_credit_the_matched_sense():
    assert evidence(
        grade(
            "CLOZE_TO_WORD",
            "SINGLE_WORD",
            {"sense_id": 2, "task_fit": True, "spelling_error": True},
        ),
        1,
    ) == (2, 1, 0.8)
    assert evidence(
        grade(
            "WORD_TO_DEFINITION",
            "SHORT_ANSWER",
            {"sense_id": 2, "accuracy": "MIXED", "coverage": "PARTIAL"},
        ),
        1,
    ) == (2, 1, 0.25)
    assert evidence(
        grade(
            "CLOZE_TO_WORD",
            "SINGLE_WORD",
            {"sense_id": 2, "task_fit": False, "spelling_error": False},
        ),
        1,
    ) == (1, 0, 0)


def test_rewrite_separates_recall_from_preservation_and_usage():
    diagnostic = dict(
        used=True,
        meaning="APPROXIMATE",
        form="SPELLING_ERROR",
        construction=True,
        collocation=False,
        appropriacy=True,
        meaning_preservation="PARTIAL",
    )
    assert evidence(grade("SENTENCE_REWRITE", "SHORT_ANSWER", diagnostic), 1) == (
        1,
        1,
        pytest.approx(0.175),
    )
    diagnostic["meaning"] = "WRONG"
    assert evidence(grade("SENTENCE_REWRITE", "SHORT_ANSWER", diagnostic), 1) == (1, 0, None)


def test_elo_uses_one_mean_budget_and_elapsed_exposure_weight(config):
    now = datetime(2026, 10, 11, tzinfo=UTC)
    policy = config.learning.mastery
    assert update_elo(800, [(1, 800)], None, now, policy) == 816
    assert update_elo(800, [(1, 800)] * 3, None, now, policy) == 816
    assert update_elo(800, [(1, 800), (0, 800)], None, now, policy) == 800
    assert update_elo(800, [(1, 800)], now, now, policy) == 800
    assert update_elo(800, [(1, 800)], now - timedelta(hours=12), now, policy) == 808
    assert update_elo(800, [(None, 800)], None, now, policy) == 800
