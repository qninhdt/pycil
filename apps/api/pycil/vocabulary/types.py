"""Typed data structures and dictionaries for vocabulary domain."""

from typing import TypedDict

from pycil.vocabulary.enums import (
    CEFRLevel,
    EntryType,
    PartOfSpeech,
    Register,
    Tier,
)


class SenseSummaryDict(TypedDict):
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


class WordAliasInsert(TypedDict):
    word_id: int
    content: str
    match_key: str


type SearchPayload = tuple[str, str, str, str, int, dict[str, list[str]] | None]
