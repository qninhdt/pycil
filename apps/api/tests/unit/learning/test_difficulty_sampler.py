"""Depth-keyed serve sampler invariants."""

import random
from collections import Counter

from pycil.policy.policy import LEVEL_PROFILES, sample_requested_level


def test_every_profile_sums_to_one():
    for band in LEVEL_PROFILES:
        assert abs(sum(band.profile.values()) - 1.0) < 1e-9


def test_depth_one_only_serves_level_one():
    rng = random.Random(42)
    assert {sample_requested_level(1, rng) for _ in range(200)} == {1}


def test_depth_four_uses_the_published_window():
    rng = random.Random(7)
    counts = Counter(sample_requested_level(4, rng) for _ in range(20000))
    freq = {k: v / 20000 for k, v in counts.items()}
    assert 1 not in freq
    assert abs(freq.get(2, 0) - 0.30) < 0.03
    assert abs(freq.get(3, 0) - 0.45) < 0.03
    assert abs(freq.get(4, 0) - 0.25) < 0.03


def test_sampled_level_always_in_1_to_4():
    rng = random.Random(1)
    for depth in range(0, 6):
        for _ in range(50):
            assert 1 <= sample_requested_level(depth, rng) <= 4


def test_exhausted_credit_removes_level_four_from_the_window():
    rng = random.Random(9)
    assert {sample_requested_level(4, rng, allow_level4=False) for _ in range(500)} <= {2, 3}
