"""Content DTOs. Sense content fields are populated from LexiClient responses,
never from pycil rows (pycil stores only opaque ``senseId`` membership)."""

from pydantic import BaseModel, Field


class WordRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class WordSearchRead(BaseModel):
    display: str
    entry_type: str | None = Field(default=None, serialization_alias="entryType")
    score: float = 0.0
    lexi_word_id: int | None = Field(default=None, serialization_alias="wordId")
    cambridge_id: int | None = Field(default=None, serialization_alias="cambridgeId")
    gloss: str | None = None


class SenseAddRequest(BaseModel):
    sense_id: int = Field(alias="senseId")

    model_config = {"populate_by_name": True}


class SenseRef(BaseModel):
    sense_id: int = Field(alias="senseId", serialization_alias="senseId")

    model_config = {"populate_by_name": True}


class SenseContent(BaseModel):
    sense_id: int | None = Field(default=None, serialization_alias="senseId")
    definition: str
    tier: str
    pos: str | None = None
    cefr_level: str | None = Field(default=None, serialization_alias="cefrLevel")
    examples: list[str] = Field(default_factory=list)
