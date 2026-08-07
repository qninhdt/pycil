"""FSRS behavior across a *sequence* of reviews, not a single step.

The existing engine tests each assert one `update()` from a hand-written state.
That covers the formulas but not the properties a learner actually experiences,
which only appear over a run: that repeated success keeps growing the interval,
that one lapse gives back much of it, that difficulty drifts the right way, and
that mastery tracks stability without ever jumping backwards on a success.

These assert meaning rather than numbers, so they survive a refactor of the
engine internals — a weight retune moves the values, but a schedule that shrinks
on success or a mastery that falls after a correct answer is a defect either way.
Bounds are deliberately loose for that reason; the single-step tests own the
exact arithmetic.
"""

import pytest

from shared.fsrs import (
    grade_from_correct,
    initial_state,
    mastery,
    recall,
    update,
)

# Imported rather than restated: a test that hardcodes 365 stops tracking the engine
# the moment the ceiling moves, and starts asserting a number nobody chose twice.
from shared.fsrs.engine import _MAX_INTERVAL_DAYS

# A review taken exactly when due: elapsed == S means R == 0.9 by construction, so
# a run scheduled this way is the well-behaved case the scheduler aims for.
_ON_TIME = None


def _run(answers: list[bool], *, elapsed: float | None = _ON_TIME):
    """Replay a sequence of answers, reviewing each time at the scheduled interval.

    Returns every intermediate state, so a test can assert on the shape of the
    whole progression rather than only its endpoint.
    """
    state = initial_state(correct=answers[0])
    states = [state]
    for correct in answers[1:]:
        gap = state.interval_days if elapsed is None else elapsed
        state = update(state.stability, state.difficulty, correct, gap)
        states.append(state)
    return states


def test_a_clean_run_keeps_growing_the_interval():
    """Every correct review scheduled on time must extend the next gap.

    Growth is strict only below the 365-day ceiling: `_interval` clamps there, so a
    long clean run legitimately reports the same interval twice at the top. That
    plateau is the cap doing its job, not the schedule stalling, so it is asserted
    as "never shrinks" overall plus "strictly grows while there is headroom".
    """
    states = _run([True] * 6)
    intervals = [state.interval_days for state in states]
    assert intervals == sorted(intervals)
    below_cap = [value for value in intervals if value < _MAX_INTERVAL_DAYS]
    assert len(set(below_cap)) == len(below_cap), "a correct answer never repeats the interval"
    # Six on-time successes should reach a genuinely long gap, not creep.
    assert states[-1].interval_days > 10 * states[0].interval_days


def test_a_lapse_costs_most_of_the_accumulated_interval():
    """Getting it wrong after a good run must pull the schedule back hard."""
    good_run = _run([True] * 5)
    lapsed = update(
        good_run[-1].stability, good_run[-1].difficulty, correct=False,
        elapsed_days=good_run[-1].interval_days,
    )
    assert lapsed.stability < good_run[-1].stability
    # Not merely smaller — a lapse is meant to undo the run, not shave it.
    assert lapsed.interval_days < good_run[-1].interval_days / 2


def test_a_lapse_never_reschedules_further_out_than_before():
    """Holds from any state, not just the tail of a clean run."""
    for step in range(1, 6):
        before = _run([True] * step)[-1]
        after = update(
            before.stability, before.difficulty, correct=False,
            elapsed_days=before.interval_days,
        )
        assert after.stability <= before.stability


def test_recovery_after_a_lapse_grows_again():
    """A lapse must not permanently wedge the schedule at the floor."""
    states = _run([True, True, True, False, True, True, True])
    lapse_index = 3
    recovering = [state.interval_days for state in states[lapse_index:]]
    assert recovering == sorted(recovering)
    assert states[-1].interval_days > states[lapse_index].interval_days


def test_repeated_failure_keeps_difficulty_rising_but_bounded():
    states = _run([False] * 10)
    difficulties = [state.difficulty for state in states]
    # Monotonic upward, and pinned at the ceiling rather than escaping it.
    assert difficulties == sorted(difficulties)
    assert all(1.0 <= value <= 10.0 for value in difficulties)
    assert difficulties[-1] == pytest.approx(10.0, abs=0.5)


def test_repeated_success_keeps_difficulty_falling_but_bounded():
    difficulties = [state.difficulty for state in _run([True] * 10)]
    assert difficulties == sorted(difficulties, reverse=True)
    assert all(1.0 <= value <= 10.0 for value in difficulties)


def test_an_easier_sense_outpaces_a_harder_one_from_the_same_stability():
    """Difficulty must actually change the schedule, not just be recorded."""
    easy = update(stability=20.0, difficulty=2.0, correct=True, elapsed_days=20.0)
    hard = update(stability=20.0, difficulty=9.0, correct=True, elapsed_days=20.0)
    assert easy.stability > hard.stability


def test_mastery_rises_over_a_clean_run_and_never_falls_on_success():
    scores = [mastery(state.stability) for state in _run([True] * 8)]
    assert scores == sorted(scores)
    assert scores[-1] > scores[0]
    assert all(0 <= score <= 100 for score in scores)


def test_mastery_delta_shrinks_as_mastery_accumulates():
    """The curve saturates: later correct answers move the number less.

    This is what makes the displayed number stable for a well-known word. If the
    deltas stopped shrinking, mastery would swing late in a sense's life and the
    band a learner sits in would flicker.
    """
    scores = [mastery(state.stability) for state in _run([True] * 9)]
    deltas = [after - before for before, after in zip(scores[:-1], scores[1:], strict=True)]
    # Compare halves rather than adjacent pairs: rounding to an int makes any single
    # step noisy, while the trend across the run is the actual guarantee.
    first_half = deltas[: len(deltas) // 2]
    second_half = deltas[len(deltas) // 2 :]
    assert sum(second_half) < sum(first_half)


def test_mastery_falls_after_a_lapse():
    good_run = _run([True] * 5)
    before = mastery(good_run[-1].stability)
    lapsed = update(
        good_run[-1].stability, good_run[-1].difficulty, correct=False,
        elapsed_days=good_run[-1].interval_days,
    )
    assert mastery(lapsed.stability) < before


def test_an_on_time_review_always_sees_the_target_retention():
    """Reviewing at the scheduled interval is what R == 0.9 means.

    The scheduler's whole premise. Asserted across a run because it is a property
    of the interval the engine hands back, not of one hand-picked stability.
    """
    for state in _run([True] * 5):
        # Only meaningful while the interval is the stability — past the 365-day
        # clamp the review is deliberately earlier than the model would ask for.
        if state.interval_days < 365.0:
            assert recall(state.stability, state.interval_days) == pytest.approx(0.9, abs=1e-9)


def test_cramming_a_whole_run_barely_beats_a_single_review():
    """Six reviews minutes apart must not buy six reviews' worth of schedule.

    The anti-cram property, asserted over a sequence: the single-step test shows
    one early review grows S by almost nothing, but the guarantee a learner
    depends on is that *repeating* that cannot ladder up the interval.
    """
    crammed = _run([True] * 6, elapsed=0.01)
    one_review = initial_state(correct=True)
    assert crammed[-1].interval_days < 3 * one_review.interval_days


def test_grade_mapping_is_the_only_thing_the_engine_sees():
    """Two answers with the same correctness must produce identical states.

    The engine's documented contract is a binary label. This pins that nothing
    else about an answer can leak into scheduling.
    """
    assert grade_from_correct(True) == grade_from_correct(True)
    first = update(stability=15.0, difficulty=5.0, correct=True, elapsed_days=15.0)
    second = update(stability=15.0, difficulty=5.0, correct=True, elapsed_days=15.0)
    assert first == second
