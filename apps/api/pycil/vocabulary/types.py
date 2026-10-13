"""Typed data structures and dictionaries for vocabulary domain."""

from typing import TypedDict
from uuid import UUID

from pycil.vocabulary.enums import (
    CEFRLevel,
    EntryType,
    GenerationStage,
    JobState,
    PartOfSpeech,
    Register,
    Tier,
)


class SensePreview(TypedDict):
    sense_id: int
    word_id: int
    lemma: str
    entry_type: EntryType | None
    pos: PartOfSpeech
    tier: Tier
    cefr_level: CEFRLevel | None
    register: Register | None
    ipa_uk: str | None
    ipa_us: str | None
    definition: str | None


class MeaningSense(TypedDict):
    id: int
    pos: PartOfSpeech
    definition: str


class MeaningInventory(TypedDict):
    id: int
    lemma: str
    senses: list[MeaningSense]


class WordNetSense(TypedDict):
    key: str
    pos: str
    definition: str


class GenerationTaskState(TypedDict):
    task_id: UUID
    status: JobState
    word_id: int | None
    stage: GenerationStage | None
    error: str | None
    status_url: str
