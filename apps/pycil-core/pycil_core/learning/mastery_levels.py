"""ELO → 11-bucket mastery level mapping.

Level 0 means "no user_term_stats row at all" (unseen). Levels 1-10 are
contiguous ELO buckets centered at 1000 = level 4/5 boundary, 100-wide each
except the tails. See plan §"Mastery Levels (11 buckets)".
"""
from __future__ import annotations


MASTERY_LABELS: dict[int, str] = {
    0: "Unseen",
    1: "Brand new",
    2: "Learning",
    3: "Familiar",
    4: "Confident-1",
    5: "Confident-2",
    6: "Strong-1",
    7: "Strong-2",
    8: "Mastered-1",
    9: "Mastered-2",
    10: "Expert",
}


def level_for_elo(elo: int) -> int:
    """Map an ELO rating to its mastery bucket (1-10)."""
    if elo < 800:
        return 1
    if elo < 900:
        return 2
    if elo < 1000:
        return 3
    if elo < 1100:
        return 4
    if elo < 1200:
        return 5
    if elo < 1300:
        return 6
    if elo < 1400:
        return 7
    if elo < 1500:
        return 8
    if elo < 1600:
        return 9
    return 10


def label_for_level(level: int) -> str:
    return MASTERY_LABELS.get(level, "Unknown")
