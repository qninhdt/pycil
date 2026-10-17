"""Pydantic validation schemas for raw imported reference lexical entries."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pycil.utils.schemas import PositiveID
from pycil.vocabulary.enums import EntryType


class SourceSense(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: PositiveID
    definition: Annotated[str, Field(min_length=1)]
    pos: str | None
    headword: str | None
    phrase_title: str | None
    ipa_uk: str | None
    ipa_us: str | None
    entry_order: Annotated[int, Field(ge=0)]
    sense_order: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def definition_present(self) -> Self:
        if not self.definition.strip():
            raise ValueError("empty source definition")
        return self


class SourceWord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: PositiveID
    lemma: Annotated[str, Field(min_length=1)]
    display_form: Annotated[str, Field(min_length=1)]
    entry_type: EntryType
    alternatives: list[tuple[str, str]]
    inflections: list[str]
    senses: Annotated[list[SourceSense], Field(min_length=1)]

    @model_validator(mode="after")
    def lexical_identity(self) -> Self:
        if not self.lemma.strip() or not self.display_form.strip():
            raise ValueError("empty reference word")
        if len({sense.id for sense in self.senses}) != len(self.senses):
            raise ValueError("duplicate source sense")
        if any(not surface.strip() for surface in self.inflections):
            raise ValueError("empty inflection")
        if any(not surface.strip() or not kind.strip() for surface, kind in self.alternatives):
            raise ValueError("empty alternative")
        return self
