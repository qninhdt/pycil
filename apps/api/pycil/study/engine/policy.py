"""Pure learning-policy constants and depth-keyed assessment sampling.

Only values that are policy *invariants* live here: they do not vary by
environment or product owner and no operator would ever tune them. The two
session shape defaults are tunable, so they are owned by
``config/config.yaml`` and read through :mod:`pycil.config` by the
planner; this module deliberately does not hold a second copy.
"""

from __future__ import annotations

import random

NEW_WORD_FLOOR = 2
ASSESSMENT_FLOOR = 1

# A depth-zero sense is not in the sampling table: its first assessment is always
# the floor. The table below is deliberately the only source for later serves.
_LevelProfile = dict[int, float]


class _Band:
    """The existing injectable probability-band mechanism, keyed by depth."""

    __slots__ = ("lo", "hi", "profile")

    def __init__(self, lo: int, hi: int, profile: _LevelProfile) -> None:
        self.lo = lo
        self.hi = hi
        self.profile = profile


LEVEL_PROFILES: tuple[_Band, ...] = (
    _Band(1, 1, {1: 1.00, 2: 0.0, 3: 0.0, 4: 0.0}),
    _Band(2, 2, {1: 0.40, 2: 0.60, 3: 0.0, 4: 0.0}),
    _Band(3, 3, {1: 0.10, 2: 0.30, 3: 0.60, 4: 0.0}),
    _Band(4, 4, {1: 0.0, 2: 0.30, 3: 0.45, 4: 0.25}),
)

for _band in LEVEL_PROFILES:
    _total = sum(_band.profile.values())
    if abs(_total - 1.0) > 1e-9:
        raise AssertionError(
            f"level profile for depth {_band.lo}-{_band.hi} sums to {_total}, expected 1.0"
        )
del _band, _total


def depth_band(depth_level: int) -> _Band:
    """Return the sampling band for depth 1..4, clamping invalid input defensively."""
    clamped = max(1, min(4, depth_level))
    for band in LEVEL_PROFILES:
        if band.lo <= clamped <= band.hi:
            return band
    return LEVEL_PROFILES[-1]


def sample_requested_level(
    depth_level: int,
    rng: random.Random | None = None,
    *,
    allow_level4: bool = True,
) -> int:
    """Sample a serve level, dropping level 4 when its usage quota is exhausted."""
    if depth_level <= 0:
        return ASSESSMENT_FLOOR
    picker = rng if rng is not None else random.Random()
    profile = depth_band(depth_level).profile
    if not allow_level4 and profile.get(4, 0.0) > 0:
        profile = {level: weight for level, weight in profile.items() if level != 4}
        total = sum(profile.values())
        profile = {level: weight / total for level, weight in profile.items()}
    point = picker.random()
    accumulated = 0.0
    last_level = ASSESSMENT_FLOOR
    for level in sorted(profile):
        weight = profile[level]
        if weight <= 0.0:
            continue
        last_level = level
        accumulated += weight
        if point < accumulated:
            return level
    return last_level


# Depth owns the stage labels. Strength remains the numeric mastery projection
# from FSRS; it must not choose a depth label.
DEPTH_STAGE_NAMES: tuple[str, ...] = (
    "New",
    "Recognised",
    "Familiar",
    "Applied",
    "Fluent",
)


def depth_stage(depth_level: int) -> int:
    """Return the zero-based stage for depth 0..4."""
    return max(0, min(len(DEPTH_STAGE_NAMES) - 1, depth_level))


def depth_stage_name(depth_level: int) -> str:
    """Return the display label owned by the depth axis."""
    return DEPTH_STAGE_NAMES[depth_stage(depth_level)]


# Strength remains a separate display axis from learning depth.
STRENGTH_STAGE_NAMES: tuple[str, ...] = (
    "New",
    "Recognised",
    "Familiar",
    "Applied",
    "Fluent",
)
MASTERED_FLOOR = 80


#: Inclusive upper bound of each strength band, in order; index + 1 is the stage.
#: These are the same bounds the web's `mastery.generated.ts` renders, and
#: `tests/unit/architecture/test_web_mastery_bands_match_policy.py` fails if the two
#: drift. The band is a display concept only: strength schedules through FSRS, so
#: nothing here samples from it the way `LEVEL_PROFILES` samples from depth.
_STRENGTH_BOUNDS = (10, 30, 55, 80)


def strength_stage(mastery: int) -> int:
    """Return the one-based display stage for a strength score."""
    clamped = max(0, min(100, mastery))
    for index, bound in enumerate(_STRENGTH_BOUNDS):
        if clamped <= bound:
            return index + 1
    return len(_STRENGTH_BOUNDS) + 1


def strength_stage_name(mastery: int) -> str:
    """Return the display label for a strength score."""
    return STRENGTH_STAGE_NAMES[strength_stage(mastery) - 1]
