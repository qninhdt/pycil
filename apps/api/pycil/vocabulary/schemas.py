"""Detached lexical response values; ORM entities stay inside persistence operations."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from pycil.vocabulary.enums import (
    CEFRLevel,
    EntryType,
    GenerationState,
    HitKind,
    Inflection,
    MatchKind,
    PartOfSpeech,
    Register,
    ResolutionState,
    SenseRelationType,
    Tier,
    WordRelationType,
)


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, serialize_by_alias=True)
    id: int
    content: str
    theme_id: int | None = None


class Example(Definition):
    pass


class Form(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, serialize_by_alias=True)
    surface: str
    inf: Inflection


class SenseRelation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, serialize_by_alias=True)
    rel_type: SenseRelationType
    to_word_id: int
    to_word_lemma: str
    resolution_state: ResolutionState
    to_sense_id: int | None = None


class WordRelation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, serialize_by_alias=True)
    rel_type: WordRelationType
    to_word_id: int
    to_word_lemma: str


class Sense(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, serialize_by_alias=True)
    id: int
    word_id: int
    pos: PartOfSpeech
    tier: Tier
    definition: Definition | None = None
    examples: list[Example] = Field(default_factory=lambda: [])
    forms: list[Form] = Field(default_factory=lambda: [])
    patterns: list[str] = Field(default_factory=list)
    collocations: list[str] = Field(default_factory=list)
    relations: list[SenseRelation] = Field(default_factory=lambda: [])
    cefr_level: CEFRLevel | None = None
    register_: Register | None = Field(default=None, alias="register")
    ipa_uk: str | None = None
    ipa_us: str | None = None


class Word(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, serialize_by_alias=True)
    id: int
    lemma: str
    type: EntryType
    generation_state: GenerationState
    senses: list[Sense] = Field(default_factory=lambda: [])
    aliases: list[str] = Field(default_factory=list)
    related: list[WordRelation] = Field(default_factory=lambda: [])


class WordHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, serialize_by_alias=True)
    word_id: int
    lemma: str
    entry_type: EntryType
    match_kind: MatchKind
    matched_surface: str
    kind: Literal[HitKind.WORD] = HitKind.WORD


class ReferenceHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, serialize_by_alias=True)
    reference_id: str
    display: str
    entry_type: EntryType
    match_kind: MatchKind
    matched_surface: str
    kind: Literal[HitKind.REFERENCE] = HitKind.REFERENCE


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, serialize_by_alias=True)
    items: list[Annotated[WordHit | ReferenceHit, Field(discriminator="kind")]] = Field(
        default_factory=lambda: []
    )
