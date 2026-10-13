from typing import Annotated

from pydantic import Field

from pycil.infrastructure.configuration import NonnegativeInt, Policy, PositiveInt


class GenerationPolicy(Policy):
    question_artifact_batch_size: Annotated[int, Field(strict=True, ge=1, le=20)]
    correct_count: Annotated[int, Field(strict=True, ge=1, le=20)]
    distractor_count: Annotated[int, Field(strict=True, ge=3, le=20)]
    examples_per_sense: PositiveInt
    timeout_seconds: PositiveInt


class VocabularyPolicy(Policy):
    model: str
    timeout_seconds: Annotated[int, Field(strict=True, ge=1, le=120)]
    max_completion_tokens: Annotated[int, Field(strict=True, ge=1, le=32768)]
    max_retries: NonnegativeInt
    structured_outputs: Annotated[bool, Field(strict=True)]
    reasoning_effort: str | None
    temperature: Annotated[float, Field(ge=0, le=2)] | None
    decision_model: str
