"""Transport and retry settings for model provider clients."""

from typing import Annotated, Self

from pydantic import Field, model_validator

from pycil.utils.configuration import NonnegativeInt, Policy


class ProviderPolicy(Policy):
    model: str = "openai/gpt-6.1-sol"
    timeout_seconds: Annotated[int, Field(strict=True, ge=1, le=120)] = 120
    max_completion_tokens: Annotated[int, Field(strict=True, ge=1, le=32768)] = 16384
    max_retries: NonnegativeInt = 2
    structured_outputs: Annotated[bool, Field(strict=True)] = True
    reasoning_effort: str | None = "medium"
    temperature: Annotated[float, Field(ge=0, le=2)] | None = None
    decision_model: str = "typesafe/jev-1.13"

    retry_min_seconds: Annotated[float, Field(strict=True, gt=0)] = 0.5
    retry_max_seconds: Annotated[float, Field(strict=True, gt=0)] = 8.0

    @model_validator(mode="after")
    def retry_bounds(self) -> Self:
        if self.retry_min_seconds > self.retry_max_seconds:
            raise ValueError("retry minimum exceeds maximum")
        return self
