from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from pycil.infrastructure.configuration import Policy, PositiveInt


class AssistantPreferences(Policy):
    auto_approve: Annotated[bool, Field(strict=True)]


class AssistantPolicy(Policy):
    default_model: str
    default_effort: str
    llm_timeout_seconds: PositiveInt
    max_tool_calls: PositiveInt
    max_message_chars: PositiveInt
    max_context_messages: PositiveInt
    max_images: PositiveInt
    max_image_bytes: PositiveInt
    starts_per_minute: PositiveInt


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
