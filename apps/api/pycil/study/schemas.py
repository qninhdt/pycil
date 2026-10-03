from uuid import UUID

from lexi_ai import ResponseFormat
from pydantic import BaseModel, ConfigDict, Field

from pycil.study.models import Rating


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Prepare(Strict):
    node_id: UUID


class Grade(Strict):
    question_id: int = Field(gt=0)
    format: ResponseFormat
    answer: str = Field(min_length=1)


class Review(Strict):
    sense_id: int = Field(gt=0)
    rating: Rating
