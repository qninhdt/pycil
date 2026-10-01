"""Internal billing values and external allowance responses."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pycil.billing.plans import FeatureKey, PlanKey


@dataclass(frozen=True, slots=True)
class UsageAllowance:
    plan: PlanKey
    period_id: UUID
    period_start: datetime
    period_end: datetime
    allowance_units: int
    used_units: int
    remaining_units: int

    @property
    def raw_remaining_units(self) -> int:
        return self.allowance_units - self.used_units

    def as_dict(self) -> dict:
        return {
            "period_id": str(self.period_id),
            "plan": self.plan.value,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "allowance_units": self.allowance_units,
            "used_units": self.used_units,
            "remaining_units": self.remaining_units,
            "raw_remaining_units": self.raw_remaining_units,
            "consumed_units": self.used_units,
            "available_units": self.remaining_units,
            "raw_balance_units": self.raw_remaining_units,
        }


@dataclass(frozen=True, slots=True)
class UsageSettlement:
    event_id: UUID
    event_key: str
    period_id: UUID
    feature_key: FeatureKey
    units: int
    idempotent_replay: bool


class UsageAllowanceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    plan: PlanKey
    period_start: datetime = Field(alias="periodStart", validation_alias="period_start")
    period_end: datetime = Field(alias="periodEnd", validation_alias="period_end")
    allowance_units: int = Field(alias="allowanceUnits", validation_alias="allowance_units")
    used_units: int = Field(alias="usedUnits", validation_alias="used_units")
    remaining_units: int = Field(alias="remainingUnits", validation_alias="remaining_units")


class CreditBalanceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    plan: PlanKey
    period_start: datetime = Field(alias="periodStart", validation_alias="period_start")
    period_end: datetime = Field(alias="periodEnd", validation_alias="period_end")
    allowance_units: int = Field(alias="allowanceUnits", validation_alias="allowance_units")
    consumed_units: int = Field(alias="consumedUnits", validation_alias="consumed_units")
    available_units: int = Field(alias="availableUnits", validation_alias="available_units")
