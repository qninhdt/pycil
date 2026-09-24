"""Request and response payloads for account-owned lifecycle operations."""

from datetime import datetime

from pydantic import BaseModel

from pycil.account.plans import AccountPlan


class AccountDeleteRequest(BaseModel):
    confirmation: str


class AccountCredit(BaseModel):
    """The learner's monthly allowance.

    Reported in Credits and milli-credits, never in a currency. ``available`` is
    the balance clamped to zero for display, while ``balance`` stays signed
    because a turn admitted with a positive balance is allowed to finish and may
    drive it slightly negative.
    """

    plan: AccountPlan
    balance: int
    available: int
    period_start: datetime
    period_end: datetime
    period_used: int
    period_grant: int
    topup_balance: int


class AccountExport(BaseModel):
    profile: dict
    hierarchy: list[dict]
    learning: dict
    assistant: dict
    plan: AccountPlan
    credit: AccountCredit
