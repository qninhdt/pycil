from typing import Self, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pycil.vocabulary.enums import (
    CEFRLevel,
    EntryType,
    PartOfSpeech,
    Register,
    SenseRelationType,
    Tier,
    WordRelationType,
)
from pycil.vocabulary.patterns import validate_pattern
from pycil.vocabulary.text import (
    answer_key,
    canonical_markup,
    parse_form,
    parse_marked_example,
    strip_markup,
    validate_lemma,
)


class InventorySense(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: str = Field(min_length=1, max_length=16000)
    pos: PartOfSpeech
    references: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def meaningful_definition(self) -> Self:
        if not self.definition.strip() or len(set(self.references)) != len(self.references):
            raise ValueError("invalid sense evidence")
        return self


class RelatedWords(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: WordRelationType
    lemmas: list[str] = Field(min_length=1)


class RelatedSenses(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: SenseRelationType
    lemmas: list[str] = Field(min_length=1)


class Inventory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lemma: str
    type: EntryType
    aliases: list[str]
    related: list[RelatedWords]
    senses: list[InventorySense] = Field(min_length=1)

    @field_validator("lemma")
    @classmethod
    def citation(cls, value: str) -> str:
        return validate_lemma(value)

    @model_validator(mode="after")
    def consistent_inventory(self) -> Self:
        for lemma in [
            *self.aliases,
            *(lemma for group in self.related for lemma in group.lemmas),
        ]:
            validate_lemma(lemma)
            if parse_marked_example(lemma)[1]:
                raise ValueError("lexical identities must be plain text")
        if any(group.type is WordRelationType.PART_OF_PHRASAL_FAMILY for group in self.related):
            raise ValueError("phrasal families come from source evidence")
        identities = [(sense.pos, answer_key(sense.definition)) for sense in self.senses]
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate inventory sense")
        return self


class Enrichment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sense_id: int = Field(ge=1)
    tier: Tier
    examples: list[str] = Field(min_length=1)
    forms: list[str]
    patterns: list[str]
    collocations: list[str]
    relations: list[RelatedSenses]
    cefr_level: CEFRLevel
    register_: Register | None = Field(alias="register")

    @field_validator("examples", mode="before")
    @classmethod
    def usable_examples(cls, values: object) -> object:
        if not isinstance(values, list):
            return values
        accepted: list[str] = []
        seen: set[str] = set()
        items: list[object] = cast(list[object], values)
        for raw_value in items:
            if not isinstance(raw_value, str):
                continue
            try:
                canonical = canonical_markup(raw_value)
                if not parse_marked_example(canonical)[1]:
                    continue
                key = answer_key(strip_markup(canonical))
            except ValueError:
                continue
            if key not in seen:
                seen.add(key)
                accepted.append(canonical)
        if not accepted:
            raise ValueError("sense needs at least one example with valid target markup")
        return accepted

    @model_validator(mode="after")
    def valid_details(self) -> Self:
        for form in self.forms:
            parse_form(form)
        for pattern in self.patterns:
            validate_pattern(pattern)
        for value in [
            *self.collocations,
            *(lemma for group in self.relations for lemma in group.lemmas),
        ]:
            if parse_marked_example(value)[1]:
                raise ValueError("relations and collocations must be plain text")
        for group in self.relations:
            for lemma in group.lemmas:
                validate_lemma(lemma)
        return self


class EnrichmentBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    senses: list[Enrichment] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def distinct_senses(self) -> Self:
        if len({sense.sense_id for sense in self.senses}) != len(self.senses):
            raise ValueError("duplicate enrichment identity")
        return self


def validate_inventory(inventory: Inventory, sources: set[str]) -> None:
    if any(not set(sense.references) <= sources for sense in inventory.senses):
        raise ValueError("inventory cites evidence that was not supplied")
