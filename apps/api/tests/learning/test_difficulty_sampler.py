"""Difficulty sampler: non-uniform mastery profiles, sum-to-1 (acceptance #9)."""

import random
from collections import Counter

from pycil.learning.policy import LEVEL_PROFILES, mastery_band, sample_requested_level


def test_every_profile_sums_to_one():
    for band in LEVEL_PROFILES:
        assert abs(sum(band.profile.values()) - 1.0) < 1e-9


def test_mastery_band_selection():
    assert mastery_band(5).hi == 10
    assert mastery_band(20).hi == 30
    assert mastery_band(100).lo == 81


def test_low_mastery_favors_level_1():
    rng = random.Random(42)
    counts = Counter(sample_requested_level(5, rng) for _ in range(20000))
    freq = {k: v / 20000 for k, v in counts.items()}
    assert abs(freq.get(1, 0) - 0.90) < 0.03
    assert abs(freq.get(2, 0) - 0.10) < 0.03
    assert 3 not in freq and 4 not in freq


def test_high_mastery_favors_higher_levels():
    rng = random.Random(7)
    counts = Counter(sample_requested_level(90, rng) for _ in range(20000))
    freq = {k: v / 20000 for k, v in counts.items()}
    assert 1 not in freq
    assert abs(freq.get(3, 0) - 0.50) < 0.03
    assert abs(freq.get(4, 0) - 0.40) < 0.03


def test_sampled_level_always_in_1_to_4():
    rng = random.Random(1)
    for mastery in range(0, 101, 5):
        for _ in range(50):
            assert 1 <= sample_requested_level(mastery, rng) <= 4
