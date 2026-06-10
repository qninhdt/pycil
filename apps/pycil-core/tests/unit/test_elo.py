"""Unit tests for pycil_core.learning.elo.

Run with: `pytest pycil_core/learning/elo_test.py -v`.
"""
from __future__ import annotations

import math

import pytest

from pycil_core.learning import elo


def test_constants_are_consistent() -> None:
    assert elo.MIN_ELO < elo.INITIAL_ELO < elo.MAX_ELO
    assert elo.INITIAL_INTERVAL_SECONDS == 1800


def test_realized_score_bounds() -> None:
    assert elo.realized_score(0, 2) == 0.0
    assert elo.realized_score(1, 2) == 0.5
    assert elo.realized_score(2, 2) == 1.0
    # Defensive: more correct than required gets clamped to 1.
    assert elo.realized_score(5, 2) == 1.0
    assert elo.realized_score(0, 0) == 0.0


def test_expected_score_per_question_equals_half_when_equal() -> None:
    assert elo.expected_score_per_question(1000, 1000) == pytest.approx(0.5)


def test_expected_score_per_question_higher_user_wins() -> None:
    favored = elo.expected_score_per_question(1500, 1000)
    underdog = elo.expected_score_per_question(500, 1000)
    assert favored > 0.5 > underdog
    # Symmetry: expectations sum to 1 when ratings are mirrored.
    assert favored + underdog == pytest.approx(1.0, rel=1e-6)


def test_expected_score_average_across_questions() -> None:
    es = elo.expected_score(1000, [800, 1000, 1200])
    direct = (
        elo.expected_score_per_question(1000, 800)
        + elo.expected_score_per_question(1000, 1000)
        + elo.expected_score_per_question(1000, 1200)
    ) / 3
    assert es == pytest.approx(direct)


def test_expected_score_empty_questions_returns_neutral() -> None:
    assert elo.expected_score(1000, []) == 0.5


def test_lapsed_time_factor_cold_start_is_full_weight() -> None:
    """Cold start: no prior review → T=1.0 (NOT zero — that would freeze ELO)."""
    assert elo.lapsed_time_factor(None, 1800) == 1.0
    assert elo.lapsed_time_factor(0, 1800) == 1.0
    assert elo.lapsed_time_factor(-5, 1800) == 1.0


def test_lapsed_time_factor_zero_interval_is_safe() -> None:
    assert elo.lapsed_time_factor(60, 0) == 1.0
    assert elo.lapsed_time_factor(60, -1) == 1.0


def test_lapsed_time_factor_alpha_decay_shape() -> None:
    """ALPHA=0.5 → factor = sqrt(lapsed/interval). Larger lapse → larger T."""
    half = elo.lapsed_time_factor(900, 1800)  # 0.5
    full = elo.lapsed_time_factor(1800, 1800)  # 1.0
    double = elo.lapsed_time_factor(3600, 1800)  # 2.0
    assert half == pytest.approx(math.sqrt(0.5))
    assert full == pytest.approx(1.0)
    assert double == pytest.approx(math.sqrt(2.0))


def test_elo_delta_signs() -> None:
    assert elo.elo_delta(R=1.0, E=0.5, T=1.0) > 0
    assert elo.elo_delta(R=0.0, E=0.5, T=1.0) < 0
    assert elo.elo_delta(R=0.5, E=0.5, T=1.0) == 0


def test_new_elo_clamps_to_bounds() -> None:
    assert elo.new_elo(2990, 100) == elo.MAX_ELO
    assert elo.new_elo(50, -200) == elo.MIN_ELO
    assert elo.new_elo(1000, 32) == 1032


def test_new_interval_holds_on_failure() -> None:
    """Failed review (Δ<0) must keep interval unchanged at floor."""
    out = elo.new_interval_seconds(elo_old=1000, elo_new=900, interval_old=0)
    assert out == elo.INITIAL_INTERVAL_SECONDS

    out2 = elo.new_interval_seconds(elo_old=1000, elo_new=900, interval_old=7200)
    assert out2 == 7200


def test_new_interval_grows_on_success() -> None:
    """Successful review with Δ>0 grows by F^(Δ/S)."""
    grew = elo.new_interval_seconds(elo_old=1000, elo_new=1100, interval_old=3600)
    expected = 3600 * (elo.F ** (100 / elo.S))
    assert grew == pytest.approx(expected)


def test_new_interval_first_review_uses_floor() -> None:
    """interval_old=0 must floor at INITIAL_INTERVAL_SECONDS so growth ≠ 0."""
    out = elo.new_interval_seconds(elo_old=1000, elo_new=1100, interval_old=0)
    expected = elo.INITIAL_INTERVAL_SECONDS * (elo.F ** (100 / elo.S))
    assert out == pytest.approx(expected)
    assert out > elo.INITIAL_INTERVAL_SECONDS


def test_synthetic_session_does_not_runaway() -> None:
    """100 random correct/incorrect reviews — ELO must stay in bounds."""
    import random

    random.seed(0)
    user = elo.INITIAL_ELO
    interval = 0.0
    last_lapsed: float | None = None
    for _ in range(100):
        R = float(random.choice([0, 0.5, 1]))
        E = elo.expected_score(user, [1000])
        T = elo.lapsed_time_factor(last_lapsed, interval)
        d = elo.elo_delta(R, E, T)
        new_user = elo.new_elo(user, d)
        interval = elo.new_interval_seconds(user, new_user, interval)
        user = new_user
        last_lapsed = interval
        assert elo.MIN_ELO <= user <= elo.MAX_ELO
        # Interval bounded: 100 reviews × max growth still under ~2 months.
        assert interval < 60 * 60 * 24 * 70
