"""Immutable reference identity and the fields consumed by lexical generation/search."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pycil.infrastructure.database import Base, enum_column
from pycil.vocabulary.enums import EntryType

PositiveID = Annotated[int, Field(strict=True, gt=0)]


class ReferenceSense(Base):
    __tablename__ = "reference_senses"
    __table_args__ = (
        CheckConstraint("length(btrim(definition)) > 0", name="definition_present"),
        CheckConstraint("entry_order >= 0 AND sense_order >= 0", name="source_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    word_id: Mapped[int] = mapped_column(
        ForeignKey("reference_words.id", ondelete="RESTRICT"), index=True
    )
    definition: Mapped[str] = mapped_column(Text)
    pos: Mapped[str | None] = mapped_column(Text)
    headword: Mapped[str | None] = mapped_column(Text)
    phrase_title: Mapped[str | None] = mapped_column(Text)
    ipa_uk: Mapped[str | None] = mapped_column(Text)
    ipa_us: Mapped[str | None] = mapped_column(Text)
    entry_order: Mapped[int] = mapped_column()
    sense_order: Mapped[int] = mapped_column()


class ReferenceWord(Base):
    __tablename__ = "reference_words"
    __table_args__ = (
        CheckConstraint("length(btrim(lemma)) > 0", name="lemma_present"),
        CheckConstraint("length(btrim(display_form)) > 0", name="display_present"),
        CheckConstraint(
            "jsonb_typeof(alternatives) = 'array' AND jsonb_typeof(inflections) = 'array'",
            name="search_surfaces",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    lemma: Mapped[str] = mapped_column(Text)
    display_form: Mapped[str] = mapped_column(Text)
    entry_type: Mapped[EntryType] = mapped_column(enum_column(EntryType))
    alternatives: Mapped[list[list[str]]] = mapped_column(JSONB)
    inflections: Mapped[list[str]] = mapped_column(JSONB)


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
    def definition_present(self) -> SourceSense:
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
    def lexical_identity(self) -> SourceWord:
        if not self.lemma.strip() or not self.display_form.strip():
            raise ValueError("empty reference word")
        if len({sense.id for sense in self.senses}) != len(self.senses):
            raise ValueError("duplicate source sense")
        if any(not surface.strip() for surface in self.inflections):
            raise ValueError("empty inflection")
        if any(not surface.strip() or not kind.strip() for surface, kind in self.alternatives):
            raise ValueError("empty alternative")
        return self
