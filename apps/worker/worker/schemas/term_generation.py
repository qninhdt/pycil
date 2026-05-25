"""Pydantic schemas for LLM term-generation output.

Strict validation rejects malformed JSON; output sanitization (strip URLs/HTML/
control chars) runs in the job, not here.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

CefrLevel = Annotated[
    str, StringConstraints(pattern=r"^(A1|A2|B1|B2|C1|C2)$")
]


class PartOfSpeech(str, Enum):
    NOUN = "NOUN"
    VERB = "VERB"
    ADJECTIVE = "ADJECTIVE"
    ADVERB = "ADVERB"
    PRONOUN = "PRONOUN"
    PREPOSITION = "PREPOSITION"
    CONJUNCTION = "CONJUNCTION"
    INTERJECTION = "INTERJECTION"
    DETERMINER = "DETERMINER"
    NUMERAL = "NUMERAL"
    PARTICLE = "PARTICLE"
    OTHER = "OTHER"


class GeneratedDefinition(BaseModel):
    part_of_speech: PartOfSpeech
    cefr_level: CefrLevel
    canonical_meaning: str = Field(min_length=4, max_length=400)
    synonyms: list[str] = Field(default_factory=list, max_length=10)
    antonyms: list[str] = Field(default_factory=list, max_length=10)


class GeneratedParaphrase(BaseModel):
    value: str = Field(min_length=4, max_length=400)
    cefr_level: CefrLevel


class GeneratedExample(BaseModel):
    value: str = Field(min_length=4, max_length=400)
    cefr_level: CefrLevel


class TermGenerationOutput(BaseModel):
    """Strict shape the LLM is asked to return."""

    definition: GeneratedDefinition
    paraphrases: list[GeneratedParaphrase] = Field(min_length=2, max_length=4)
    examples: list[GeneratedExample] = Field(min_length=2, max_length=4)
