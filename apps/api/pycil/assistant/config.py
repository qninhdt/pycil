from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from pycil.utils.configuration import Policy, PositiveInt

PositiveSeconds = Annotated[float, Field(strict=True, gt=0)]


class AssistantPreferences(Policy):
    auto_approve: Annotated[bool, Field(strict=True)] = False


class AssistantDefaults(Policy):
    model: str
    effort: str


class AssistantLimits(Policy):
    max_tool_calls: PositiveInt
    max_message_chars: PositiveInt
    max_context_messages: PositiveInt
    max_images: PositiveInt
    max_image_bytes: PositiveInt


class ModelPolicy(Policy):
    id: str
    name: str
    vision: Annotated[bool, Field(strict=True)]
    efforts: list[str]
    max_output_tokens: PositiveInt
    input_units_per_token: Annotated[Decimal, Field(ge=0)]
    output_units_per_token: Annotated[Decimal, Field(ge=0)]
    cached_read_units_per_token: Annotated[Decimal, Field(ge=0)]
    cache_write_units_per_token: Annotated[Decimal, Field(ge=0)] | None

    @model_validator(mode="after")
    def validate_model(self) -> Self:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("model identifiers must not be blank")
        if not self.efforts or len(set(self.efforts)) != len(self.efforts):
            raise ValueError("model efforts must be nonempty and unique")
        if any(not effort.strip() for effort in self.efforts):
            raise ValueError("model effort must not be blank")
        if any(effort not in {"low", "medium", "high"} for effort in self.efforts):
            raise ValueError("model effort must be one of: low, medium, high")
        return self


class AssistantConfig(Policy):
    defaults: AssistantDefaults
    limits: AssistantLimits
    models: list[ModelPolicy]
    llm_timeout_seconds: PositiveSeconds = 180.0
    lease_ttl_seconds: PositiveSeconds = 30.0
    starts_per_minute: PositiveInt = 20

    @model_validator(mode="after")
    def validate_assistant(self) -> Self:
        by_id = {model.id: model for model in self.models}
        if len(by_id) != len(self.models):
            raise ValueError("duplicate model ID")
        default = by_id.get(self.defaults.model)
        if default is None or self.defaults.effort not in default.efforts:
            raise ValueError("default assistant model/effort is unavailable")
        return self


class AssistantPatch(Policy):
    auto_approve: Annotated[bool, Field(strict=True)] | None = None

    @model_validator(mode="after")
    def no_explicit_null(self) -> Self:
        if "auto_approve" in self.model_fields_set and self.auto_approve is None:
            raise ValueError("assistant preferences cannot be null")
        return self
