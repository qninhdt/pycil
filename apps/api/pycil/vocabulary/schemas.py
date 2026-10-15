"""Detached lexical response values; ORM entities stay inside persistence operations."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic.dataclasses import dataclass

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

# dataclasses.replace passes Python field names, including register_.
_LEXICAL = ConfigDict(extra="forbid", serialize_by_alias=True, validate_by_name=True)


@dataclass(slots=True, frozen=True, kw_only=True, config=_LEXICAL)
class Definition:
    id: int
    content: str
    theme_id: int | None = None


@dataclass(slots=True, frozen=True, kw_only=True, config=_LEXICAL)
class Example(Definition):
    pass


@dataclass(slots=True, frozen=True, kw_only=True, config=_LEXICAL)
class Form:
    surface: str
    inf: Inflection


@dataclass(slots=True, frozen=True, kw_only=True, config=_LEXICAL)
class SenseRelation:
    rel_type: SenseRelationType
    to_word_id: int
    to_word_lemma: str
    resolution_state: ResolutionState
    to_sense_id: int | None = None


@dataclass(slots=True, frozen=True, kw_only=True, config=_LEXICAL)
class WordRelation:
    rel_type: WordRelationType
    to_word_id: int
    to_word_lemma: str


@dataclass(slots=True, frozen=True, kw_only=True, config=_LEXICAL)
class Sense:
    id: int
    word_id: int
    pos: PartOfSpeech
    tier: Tier
    definition: Definition | None = None
    examples: tuple[Example, ...] = Field(default_factory=tuple)
    forms: tuple[Form, ...] = Field(default_factory=tuple)
    patterns: tuple[str, ...] = Field(default_factory=tuple)
    collocations: tuple[str, ...] = Field(default_factory=tuple)
    relations: tuple[SenseRelation, ...] = Field(default_factory=tuple)
    cefr_level: CEFRLevel | None = None
    register_: Register | None = Field(default=None, alias="register")
    ipa_uk: str | None = None
    ipa_us: str | None = None


@dataclass(slots=True, frozen=True, kw_only=True, config=_LEXICAL)
class CachedWord:
    id: int
    lemma: str
    type: EntryType
    generation_state: GenerationState
    sense_ids: tuple[int, ...] = Field(default_factory=tuple)
    aliases: tuple[str, ...] = Field(default_factory=tuple)
    related: tuple[WordRelation, ...] = Field(default_factory=tuple)


sense_adapter = TypeAdapter(Sense)
forms_adapter = TypeAdapter(tuple[Form, ...])


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


class GenerateWord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference_id: str = Field(min_length=1, max_length=64)
