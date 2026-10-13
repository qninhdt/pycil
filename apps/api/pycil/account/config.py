from zoneinfo import ZoneInfo

from pydantic import model_validator

from pycil.account.plans import Feature
from pycil.assistant.config import AssistantPreferences
from pycil.infrastructure.configuration import NonnegativeInt, Policy


class PlanPolicy(Policy):
    monthly_allowance_units: NonnegativeInt
    features: list[Feature]


class AccountDefaults(Policy):
    locale: str
    timezone: str
    translation_language: str
    assistant: AssistantPreferences


class AccountPolicy(Policy):
    defaults: AccountDefaults
    locales: list[str]
    translation_languages: list[str]

    @model_validator(mode="after")
    def validate_defaults(self):
        try:
            ZoneInfo(self.defaults.timezone)
        except (KeyError, ValueError) as exc:
            raise ValueError("invalid default timezone") from exc
        for values in (self.locales, self.translation_languages):
            if not values or len(values) != len(set(values)) or any(not v.strip() for v in values):
                raise ValueError("supported language lists must be nonempty and unique")
        if self.defaults.locale not in self.locales:
            raise ValueError("default locale is unsupported")
        if self.defaults.translation_language not in self.translation_languages:
            raise ValueError("default translation language is unsupported")
        return self
