"""Named invariants for the independent depth axis."""

from pycil.study.engine.depth import MAX_DEPTH, next_depth_state


def test_wrong_answer_recedes_one_level_and_clears_streak():
    assert next_depth_state(3, 1, 3, False) == (2, 0)
    assert next_depth_state(1, 1, 1, False) == (1, 0)


def test_correct_at_served_depth_needs_two_clean_passes_to_advance():
    assert next_depth_state(2, 0, 2, True) == (2, 1)
    assert next_depth_state(2, 1, 2, True) == (3, 0)


def test_correct_below_current_depth_does_not_advance():
    assert next_depth_state(3, 1, 1, True) == (3, 1)


def test_first_grade_enters_floor_and_caps_at_maximum():
    assert next_depth_state(0, 0, 1, True) == (1, 1)
    assert next_depth_state(0, 0, 1, False) == (1, 0)
    assert next_depth_state(MAX_DEPTH, 1, MAX_DEPTH, True) == (MAX_DEPTH, 0)
