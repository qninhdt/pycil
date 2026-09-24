"""Discrete mastery [0-100] from stability — saturating, monotonic in S.

mastery = round(100·S/(S+30)). Uses S (not R) because R oscillates hourly and
is unstable to display; S has physical meaning ("how many days it's remembered").
"""


def mastery(stability: float) -> int:
    if stability <= 0:
        return 0
    return round(100.0 * stability / (stability + 30.0))
