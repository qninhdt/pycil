"""Small, dependency-free OpenMetrics counters for internal scraping.

Metrics deliberately use only bounded names supplied by backend code. Never add
user, email, token, query, answer, or job identifiers as labels or metric names.
"""

from collections import Counter


class Metrics:
    def __init__(self) -> None:
        self._counters: Counter[str] = Counter()

    def increment(self, name: str) -> None:
        self._counters[name] += 1

    def render_openmetrics(self) -> str:
        lines: list[str] = []
        for name, value in sorted(self._counters.items()):
            metric = name.replace("-", "_").replace(".", "_")
            lines.extend((f"# TYPE {metric} counter", f"{metric} {value}"))
        return "\n".join(lines) + ("\n" if lines else "")


metrics = Metrics()
