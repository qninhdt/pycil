"""Detached lexical response values; ORM entities stay inside persistence operations."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from pydantic.dataclasses import dataclass

from pycil.library.models import NodeSpace
from pycil.study.enums import LearningState
from pycil.utils.schemas import PositiveID, Strict
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


class WordIDs(Strict):
    word_ids: list[PositiveID] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len(set(self.word_ids)) != len(self.word_ids):
            raise ValueError("duplicate word IDs")
        return self


class WordPreview(Strict):
    word_id: int
    lemma: str
    entry_type: EntryType
    senses: list[Sense]


class LearningPreview(Strict):
    state: Literal[LearningState.NEW, LearningState.DUE, LearningState.NOT_YET_DUE]
    due_at: datetime | None
    elo: float | None
    level: Annotated[int, Field(ge=1, le=5)] | None
    last_reviewed_at: datetime | None


class SourceDeck(Strict):
    id: UUID
    name: str
    owner_id: UUID
    space: NodeSpace
    editable: bool


class SenseContext(Strict):
    sense_id: int
    learning: LearningPreview
    decks: list[SourceDeck]
    deck_count: int
    decks_has_more: bool


class Context(Strict):
    as_of: datetime
    senses: list[SenseContext]
    total: int
    studied: int
    new: int
    due: int
    not_due: int
