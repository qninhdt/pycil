"""The due/new split is a policy decision, so its boundaries are pinned here.

`plan_session`'s admission had one test and it asserted only the *total* admitted
count. A total cannot see a wrong split: an implementation that admitted five due
senses and no new ones, or five new and no due, passes an assertion on `len(...)`
while being wrong about what the learner actually studies. Two separate promises
live in that arithmetic — due work comes first, and a floor of new words is
reserved even when review is plentiful — and neither was observable.

These test the two pure functions directly rather than through a planned session,
so each boundary case is one line and the failure names the case.
"""

import pytest

from pycil.study.engine.policy import NEW_WORD_FLOOR
from pycil.study.planning import DueCandidate, _admit, _slot_split


def _due(count: int) -> list[DueCandidate]:
    return [
        DueCandidate(
            sense_id=sense_id,
            mastery=50,
            depth_level=2,
            recall=0.8,
            overdue_seconds=3600.0,
        )
        for sense_id in range(count)
    ]


def test_the_new_word_floor_is_reserved_even_when_review_is_plentiful():
    """A session of nothing but review never introduces a word."""
    new_slots, due_slots = _slot_split(target=10, due_available=50)
    assert new_slots == NEW_WORD_FLOOR
    assert due_slots == 10 - NEW_WORD_FLOOR


def test_the_floor_never_costs_more_than_the_target():
    """A target below the floor cannot reserve more slots than it has."""
    new_slots, due_slots = _slot_split(target=1, due_available=0)
    assert new_slots == 1
    assert due_slots == 0


def test_scarce_review_gives_its_unused_slots_to_new_words():
    new_slots, due_slots = _slot_split(target=10, due_available=3)
    assert new_slots == 7
    assert due_slots == 3


@pytest.mark.parametrize(
    "due_count, new_count, expected_due, expected_new",
    [
        # Both plentiful: each takes its own share and nothing backfills.
        (10, 10, 3, 2),
        # Review short: its unused slots go to new words.
        (1, 10, 1, 4),
        # New short: its unused slots go to review.
        (10, 1, 4, 1),
        # Both short: the target is simply not reachable, and no slot is invented.
        (1, 1, 1, 1),
        # Empty on one side only.
        (0, 10, 0, 5),
        (10, 0, 5, 0),
    ],
)
def test_admission_backfills_the_short_side(due_count, new_count, expected_due, expected_new):
    due, new = _admit(_due(due_count), list(range(new_count)), 5, 2, 3)
    assert (len(due), len(new)) == (expected_due, expected_new)
    assert len(due) + len(new) <= 5, "the target is a cap, not a quota to fill"


def test_admission_never_exceeds_the_target():
    """Every combination of shortages still respects the cap."""
    for due_count in range(0, 8):
        for new_count in range(0, 8):
            due, new = _admit(_due(due_count), list(range(new_count)), 5, 2, 3)
            assert len(due) + len(new) <= 5


def test_admission_prefers_due_work_when_only_one_side_can_be_served():
    """The split's first promise: review is served before new words are added."""
    due, new = _admit(_due(10), list(range(10)), target=5, new_slots=2, due_slots=3)
    assert len(due) >= len(new)
    # The first due candidates are taken, not an arbitrary subset.
    assert [candidate.sense_id for candidate in due] == [0, 1, 2]
