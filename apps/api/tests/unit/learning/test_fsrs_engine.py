"""FSRS-4.5 behavior pinned to pycil-redesign/modules/learning.md."""

import math

from pycil.learning.fsrs import (
    GRADE_AGAIN,
    GRADE_GOOD,
    grade_from_correct,
    initial_state,
    mastery,
    recall,
    update,
)
from pycil.learning.fsrs.weights import W


def test_mastery_table():
    # Doc §5 worked-example table.
    assert mastery(1) == 3
    assert mastery(7) == 19
    assert mastery(30) == 50
    assert mastery(90) == 75
    assert mastery(365) == 92


def test_mastery_monotonic_and_bounded():
    assert mastery(0) == 0
    prev = -1
    for s in (0.1, 1, 5, 30, 100, 1000, 100000):
        m = mastery(s)
        assert 0 <= m <= 100
        assert m >= prev
        prev = m


def test_recall_equals_0_9_at_stability():
    # R = 0.9 exactly when elapsed == S.
    assert math.isclose(recall(30, 30), 0.9, abs_tol=1e-9)
    assert math.isclose(recall(7, 7), 0.9, abs_tol=1e-9)


def test_recall_decreases_with_time():
    assert recall(10, 1) > recall(10, 5) > recall(10, 20)


def test_grade_mapping():
    assert grade_from_correct(True) == GRADE_GOOD == 3
    assert grade_from_correct(False) == GRADE_AGAIN == 1


def test_initial_state_first_correct_uses_w2():
    st = initial_state(correct=True)
    assert st.stability == W[2]


def test_initial_state_first_wrong_uses_w0():
    st = initial_state(correct=False)
    assert st.stability == W[0]


def test_early_review_high_R_barely_grows_stability():
    # Doc §7: reviewing early (elapsed << S → high R) yields near-zero S growth.
    st = update(stability=30.0, difficulty=5.0, correct=True, elapsed_days=0.01)
    growth = st.stability - 30.0
    assert 0 <= growth < 1.0  # anti-cram: essentially flat


def test_due_review_grows_stability_more():
    early = update(30.0, 5.0, correct=True, elapsed_days=0.01).stability
    due = update(30.0, 5.0, correct=True, elapsed_days=30.0).stability
    assert due > early  # a due review (lower R) increases S more than an early one


def test_failure_never_increases_stability():
    st = update(stability=50.0, difficulty=5.0, correct=False, elapsed_days=50.0)
    assert st.stability <= 50.0


def test_interval_clamped_to_365():
    st = update(stability=10000.0, difficulty=1.0, correct=True, elapsed_days=10000.0)
    assert st.interval_days <= 365.0


def test_interval_floor_30min():
    st = update(stability=0.0001, difficulty=9.0, correct=False, elapsed_days=0.0001)
    assert st.interval_days >= 30.0 / (24.0 * 60.0)


def test_difficulty_stays_in_bounds():
    d = 5.0
    for _ in range(50):
        d = update(10.0, d, correct=False, elapsed_days=10.0).difficulty
        assert 1.0 <= d <= 10.0
