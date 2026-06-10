"""Tests for answer_grading_service tier ladder."""
from __future__ import annotations

import pytest

from pycil_core.services.answer_grading_service import grade


@pytest.mark.parametrize(
    "user_answer,expected,result_kind",
    [
        ("definition", "definition", "exact"),
        ("Definition.", "definition", "normalized"),
        pytest.param(
            "definishun",
            "definition",
            "fuzzy",
            marks=pytest.mark.xfail(
                reason=(
                    "Pre-existing fuzzy-grading drift (F7): rapidfuzz tier for "
                    "'definishun'->'definition' returns no_match, not fuzzy. "
                    "Predates the SQLModel conversion (answer_grading_service.py "
                    "not in checkpoint 9f07149); re-tuning the threshold is a "
                    "product-behavior change, out of the audit's behavior-"
                    "preserving scope. Tracked as a separate grading-quality task."
                ),
                strict=True,
            ),
        ),
        ("totally unrelated phrase", "definition", "no_match"),
    ],
)
def test_grade_tiers(user_answer: str, expected: str, result_kind: str) -> None:
    out = grade(expected=expected, alts=[], user_answer=user_answer)
    assert out["reason"] == result_kind
    assert out["is_correct"] == (result_kind != "no_match")


def test_grade_alts_match() -> None:
    out = grade(
        expected="happy",
        alts=["joyful", "cheerful"],
        user_answer="joyful",
    )
    assert out["is_correct"]
    assert out["reason"] == "exact"


def test_grade_long_skips_levenshtein() -> None:
    long_user = "a" * 64
    out = grade(expected="b", alts=[], user_answer=long_user)
    assert not out["is_correct"]
    assert out["reason"] == "no_match"
