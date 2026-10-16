from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from pycil.utils.schemas import PositiveInt

NonnegativeInt = Annotated[int, Field(strict=True, ge=0)]


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


__all__ = ["NonnegativeInt", "Policy", "PositiveInt"]
