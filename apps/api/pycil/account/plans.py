"""Account plans and the credit unit.

Every tunable number here comes from ``config/config.yaml`` through
:mod:`pycil.product_config`, so an allowance change is a config edit rather than
a code change. What remains in this module is the unit conversion and the
mapping from a stored plan value to its policy.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from pycil.product_config import system_config

#: 1 Credit = USD 0.001, and the ledger stores milli-credits, so one Credit is
#: exactly 1,000 milli-credits. This is the single conversion factor between the
#: displayed unit and the stored one.
MILLI_CREDITS_PER_CREDIT = 1_000


class AccountPlan(str, Enum):
    free = "free"
    pro = "pro"


@dataclass(frozen=True, slots=True)
class PlanLimits:
    """Account policy represented as immutable plan data."""

    #: The monthly allowance, in milli-credits.
    period_grant: int


def normalize_plan(plan: AccountPlan | str) -> AccountPlan:
    try:
        return plan if isinstance(plan, AccountPlan) else AccountPlan(plan)
    except ValueError as exc:
        raise ValueError("unknown_account_plan") from exc


def limits_for(plan: AccountPlan | str) -> PlanLimits:
    plans = system_config.app.plans
    resolved = normalize_plan(plan)
    return PlanLimits(
        period_grant=plans[resolved.value].monthly_credits * MILLI_CREDITS_PER_CREDIT
    )


def period_grant(plan: AccountPlan | str) -> int:
    return limits_for(plan).period_grant


def rubric_grading_cost() -> int:
    """Milli-credits charged for one successful rubric provider evaluation.

    Priced per *evaluation*, not per depth level: a learner answering at level 4
    with a deterministic render is graded for free, while a level-3 free-text
    answer that reaches the rubric judge costs this amount.
    """
    return int(
        (system_config.learning.rubric_grading_credits * MILLI_CREDITS_PER_CREDIT).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


class _PlansProxy:
    def __getitem__(self, key: AccountPlan) -> PlanLimits:
        return limits_for(key)

    def __iter__(self):
        return iter(AccountPlan)

    def __len__(self):
        return len(AccountPlan)

    def __contains__(self, key):
        return key in AccountPlan


PLANS = _PlansProxy()
