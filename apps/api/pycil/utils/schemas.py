"""Base Pydantic models and shared constrained types."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base model that forbids unexpected extra attributes."""

    model_config = ConfigDict(extra="forbid")


Strict = StrictModel

type PositiveID = Annotated[int, Field(strict=True, gt=0)]
type PositiveInt = PositiveID
