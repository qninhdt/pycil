from typing import Annotated, Self
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from pycil.account.plans import Feature, Plan
from pycil.utils.configuration import NonnegativeInt, Policy

PositiveSeconds = Annotated[float, Field(strict=True, gt=0)]


class PlanPolicy(Policy):
    monthly_allowance_units: NonnegativeInt
    features: list[Feature]


class AccountConfig(Policy):
    default_locale: str = "en"
    default_timezone: str = "UTC"
    default_translation_language: str = "vi"
    auto_approve_assistant: bool = False

    locales: list[str] = ["en", "vi"]
    translation_languages: list[str] = ["en", "vi"]

    plans: dict[Plan, PlanPolicy]

    profile_timeout_seconds: PositiveSeconds = 15.0
    jwks_timeout_seconds: PositiveSeconds = 30.0
    jwks_lifespan_seconds: PositiveSeconds = 300.0

    @model_validator(mode="after")
    def validate_account(self) -> Self:
        try:
            ZoneInfo(self.default_timezone)
        except (KeyError, ValueError) as exc:
            raise ValueError("invalid default timezone") from exc
        for values in (self.locales, self.translation_languages):
            if not values or len(values) != len(set(values)) or any(not v.strip() for v in values):
                raise ValueError("supported language lists must be nonempty and unique")
        if self.default_locale not in self.locales:
            raise ValueError("default locale is unsupported")
        if self.default_translation_language not in self.translation_languages:
            raise ValueError("default translation language is unsupported")
        if set(self.plans) != set(Plan):
            raise ValueError("every subscription plan must be configured")
        for plan, policy in self.plans.items():
            if len(policy.features) != len(set(policy.features)):
                raise ValueError("duplicate feature grant")
            if plan is Plan.FREE and Feature.ADVANCED_GRADING in policy.features:
                raise ValueError("Free must not grant advanced grading")
        return self
