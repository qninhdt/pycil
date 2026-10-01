"""Account plans, feature entitlements, and operational limits.

Every tunable monthly usage allowance comes from ``config/config.yaml`` through
:mod:`pycil.config`.
"""

from dataclasses import dataclass
from enum import StrEnum

from pycil.billing.units import allowance_to_units
from pycil.platform.product_config import system_config


class PlanKey(StrEnum):
    free = "free"
    pro = "pro"


class FeatureKey(StrEnum):
    ASSISTANT = "assistant"
    LEVEL4_GRADING = "level4_grading"
    ANALYTICS_ALL_TIME = "analytics_all_time"


@dataclass(frozen=True, slots=True)
class PlanDefinition:
    """Account policy represented as immutable plan data."""

    key: PlanKey
    monthly_allowance_units: int
    features: frozenset[FeatureKey]
    assistant_concurrency: int
    daily_word_generation_limit: int = 1000

    @property
    def monthly_credit_units(self) -> int:
        return self.monthly_allowance_units


def get_plan(plan: PlanKey) -> PlanDefinition:
    """Return immutable policy definition for a PlanKey."""
    plans = system_config.app.plans
    monthly_units = allowance_to_units(plans[plan.value].monthly_credits)

    if plan == PlanKey.free:
        return PlanDefinition(
            key=PlanKey.free,
            monthly_allowance_units=monthly_units,
            features=frozenset({FeatureKey.ASSISTANT, FeatureKey.LEVEL4_GRADING}),
            assistant_concurrency=1,
            daily_word_generation_limit=1000,
        )
    return PlanDefinition(
        key=PlanKey.pro,
        monthly_allowance_units=monthly_units,
        features=frozenset(FeatureKey),
        assistant_concurrency=5,
        daily_word_generation_limit=10000,
    )


def has_feature(plan: PlanKey, feature: FeatureKey) -> bool:
    """Check whether a plan entitles access to a feature."""
    return feature in get_plan(plan).features


def rubric_grading_cost() -> int:
    """Usage units charged for one successful rubric provider evaluation."""
    return allowance_to_units(system_config.learning.rubric_grading_credits)
