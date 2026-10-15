from typing import Annotated

from pydantic import Field, model_validator

from pycil.infrastructure.configuration import NonnegativeInt, Policy, PositiveInt


class GenerationPolicy(Policy):
    examples_per_sense: PositiveInt


class SearchPolicy(Policy):
    max_query_chars: Annotated[int, Field(strict=True, ge=1, le=256)]
    default_limit: Annotated[int, Field(strict=True, ge=1, le=100)]


class VocabularyPolicy(Policy):
    model: str
    timeout_seconds: Annotated[int, Field(strict=True, ge=1, le=120)]
    max_completion_tokens: Annotated[int, Field(strict=True, ge=1, le=32768)]
    max_retries: NonnegativeInt
    structured_outputs: Annotated[bool, Field(strict=True)]
    reasoning_effort: str | None
    temperature: Annotated[float, Field(ge=0, le=2)] | None
    decision_model: str

    retry_min_seconds: Annotated[float, Field(strict=True, gt=0)]
    retry_max_seconds: Annotated[float, Field(strict=True, gt=0)]

    @model_validator(mode="after")
    def retry_bounds(self):
        if self.retry_min_seconds > self.retry_max_seconds:
            raise ValueError("retry minimum exceeds maximum")
        return self
