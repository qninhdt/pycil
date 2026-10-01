"""Small, dependency-free OpenMetrics counters for internal scraping.

Metrics deliberately use only bounded names supplied by backend code. Never add
user, email, token, query, answer, or job identifiers as labels or metric names.
"""

from collections import Counter


class Metrics:
    def __init__(self) -> None:
        self._counters: Counter[str] = Counter()

    def increment(self, name: str, value: int = 1, labels: dict[str, str] | None = None) -> None:
        if labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
            metric_key = f"{name}{{{label_str}}}"
        else:
            metric_key = name
        self._counters[metric_key] += value

    def render_openmetrics(self) -> str:
        lines: list[str] = []
        types_emitted: set[str] = set()
        for metric_key, value in sorted(self._counters.items()):
            base_name = metric_key.split("{")[0].replace("-", "_").replace(".", "_")
            if base_name not in types_emitted:
                lines.append(f"# TYPE {base_name} counter")
                types_emitted.add(base_name)
            lines.append(f"{metric_key} {value}")
        return "\n".join(lines) + ("\n" if lines else "")


metrics = Metrics()


def record_usage_period_created(plan: str) -> None:
    metrics.increment("usage_period_created_total", labels={"plan": plan})
    metrics.increment("billing_period_created_total", labels={"plan": plan})


def record_usage_settled(kind: str, units: int) -> None:
    metrics.increment("usage_recorded_total", labels={"kind": kind})
    metrics.increment("usage_units_total", value=units, labels={"kind": kind})
    metrics.increment("billing_usage_settled_total", labels={"kind": kind})
    metrics.increment("billing_usage_units_total", value=units, labels={"kind": kind})


def record_usage_idempotent_replay(kind: str) -> None:
    metrics.increment("usage_idempotent_replay_total", labels={"kind": kind})
    metrics.increment("billing_idempotent_replay_total", labels={"kind": kind})


def record_usage_recording_failure(kind: str) -> None:
    metrics.increment("usage_recording_failure_total", labels={"kind": kind})
    metrics.increment("billing_settlement_failure_total", labels={"kind": kind})


def record_usage_overage(plan: str, units: int) -> None:
    metrics.increment("usage_quota_exceeded_total", labels={"plan": plan})
    metrics.increment("usage_overage_units_total", value=units, labels={"plan": plan})
    metrics.increment("billing_overage_total", labels={"plan": plan})
    metrics.increment("billing_overage_units_total", value=units, labels={"plan": plan})


def record_plan_transition(from_plan: str, to_plan: str) -> None:
    metrics.increment(
        "plan_transition_total",
        labels={"from_plan": from_plan, "to_plan": to_plan},
    )
    metrics.increment(
        "billing_plan_transition_total",
        labels={"from_plan": from_plan, "to_plan": to_plan},
    )


def record_assistant_zero_cost() -> None:
    metrics.increment("assistant_zero_cost_segment_total")
    metrics.increment("assistant_billing_zero_cost_segment_total")
