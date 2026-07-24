"""Backend learning-policy constants + the mastery->difficulty-level sampler.

These are backend-configurable DEFAULTS (not per-user/per-deck settings): the
number of checkpoints a sense must pass, the retry budget, the new-word floor,
and the non-uniform mastery->level probability profiles the difficulty sampler
draws from.  Pure and side-effect-free; the sampler accepts an injectable RNG so
tests are deterministic.
"""

from __future__ import annotations

import random

# --- Session-planning constants -------------------------------------------------

# N: checkpoints a sense must pass (clean) before earning a Good this session.
REQUIRED_CHECKPOINTS = 2
# Retry budget per checkpoint after a wrong first attempt.
MAX_RETRIES_PER_CHECKPOINT = 2
# Minimum new senses reserved per session even under a large due backlog.
NEW_WORD_FLOOR = 2
# Backend-configurable session-shape defaults (overridable per deck via the
# JSONB ``deck_attributes.settings``; see ``planning.settings_from_deck``).
DEFAULT_TARGET_WORDS_PER_SESSION = 10
DEFAULT_MAX_QUESTIONS_PER_ROUND = 8
# Full difficulty ladder (0 = exposure, 1..4 = assessment).
DIFFICULTY_LEVELS = frozenset({0, 1, 2, 3, 4})
# Lowest assessment level; acquisition checkpoints always request this.
ASSESSMENT_FLOOR = 1

# --- Mastery -> requested-level profiles ----------------------------------------
#
# Each band maps a closed mastery range [lo, hi] to a probability distribution
# over assessment levels 1..4.  Encoded verbatim from the spec table; every row
# must sum to 1.0 (asserted at module load).

_LevelProfile = dict[int, float]


class _Band:
    __slots__ = ("lo", "hi", "profile")

    def __init__(self, lo: int, hi: int, profile: _LevelProfile) -> None:
        self.lo = lo
        self.hi = hi
        self.profile = profile


LEVEL_PROFILES: tuple[_Band, ...] = (
    _Band(0, 10, {1: 0.90, 2: 0.10, 3: 0.0, 4: 0.0}),
    _Band(11, 30, {1: 0.65, 2: 0.30, 3: 0.05, 4: 0.0}),
    _Band(31, 55, {1: 0.20, 2: 0.55, 3: 0.23, 4: 0.02}),
    _Band(56, 80, {1: 0.05, 2: 0.25, 3: 0.55, 4: 0.15}),
    _Band(81, 100, {1: 0.0, 2: 0.10, 3: 0.50, 4: 0.40}),
)

# Fail fast at import if a profile drifts from summing to 1.0.
for _band in LEVEL_PROFILES:
    _total = sum(_band.profile.values())
    if abs(_total - 1.0) > 1e-9:
        raise AssertionError(
            f"level profile for band {_band.lo}-{_band.hi} sums to {_total}, expected 1.0"
        )
del _band, _total


def mastery_band(mastery: int) -> _Band:
    """Return the profile band containing ``mastery`` (clamped to [0, 100])."""
    clamped = max(0, min(100, mastery))
    for band in LEVEL_PROFILES:
        if band.lo <= clamped <= band.hi:
            return band
    # Unreachable while the bands tile 0..100, but stay defensive.
    return LEVEL_PROFILES[-1]


def sample_requested_level(mastery: int, rng: random.Random | None = None) -> int:
    """Sample an assessment level (1..4) from the mastery band's distribution.

    ``rng`` is injectable for deterministic tests; production callers should pass a
    per-request seeded ``random.Random`` for reproducibility/analytics.  Acquisition
    does NOT use this (it always requests ``ASSESSMENT_FLOOR``).
    """
    picker = rng if rng is not None else random.Random()
    profile = mastery_band(mastery).profile
    point = picker.random()
    acc = 0.0
    last_level = ASSESSMENT_FLOOR
    for level in sorted(profile):
        weight = profile[level]
        if weight <= 0.0:
            continue
        last_level = level
        acc += weight
        if point < acc:
            return level
    # Floating-point residue: fall back to the highest non-zero level.
    return last_level
