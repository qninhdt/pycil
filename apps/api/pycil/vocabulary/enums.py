"""Controlled lexical values; member names are Python identifiers, values are wire data."""

from enum import StrEnum


class EntryType(StrEnum):
    WORD = "word"
    PHRASAL_VERB = "phrasal_verb"
    IDIOM = "idiom"
    PHRASE = "phrase"
    EXPRESSION = "expression"


class GenerationState(StrEnum):
    PENDING = "pending"
    DONE = "done"
    ERROR = "error"


class PartOfSpeech(StrEnum):
    NOUN = "noun"
    VERB = "verb"
    ADJECTIVE = "adjective"
    ADVERB = "adverb"
    PRONOUN = "pronoun"
    PREPOSITION = "preposition"
    CONJUNCTION = "conjunction"
    DETERMINER = "determiner"
    INTERJECTION = "interjection"
    NUMERAL = "numeral"
    ARTICLE = "article"
    AUXILIARY = "auxiliary"


class Tier(StrEnum):
    CORE = "core"
    COMMON = "common"
    LESS_COMMON = "less_common"
    RARE = "rare"


class Inflection(StrEnum):
    BASE = "base"
    PAST = "past"
    PAST_PARTICIPLE = "past_participle"
    PRESENT_3SG = "present_3sg"
    ING = "ing"
    PLURAL = "plural"
    COMPARATIVE = "comparative"
    SUPERLATIVE = "superlative"


class SenseRelationType(StrEnum):
    SYNONYM = "synonym"
    ANTONYM = "antonym"
    HYPERNYM = "hypernym"
    HYPONYM = "hyponym"
    MERONYM = "meronym"
    HOLONYM = "holonym"


class WordRelationType(StrEnum):
    WORD_FAMILY = "word_family"
    CONFUSED_WITH = "confused_with"
    PART_OF_PHRASAL_FAMILY = "part_of_phrasal_family"


class ResolutionState(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"
    UNRESOLVABLE = "unresolvable"
    NOOP = "noop"
    ERROR = "error"


class CEFRLevel(StrEnum):
    A1 = "a1"
    A2 = "a2"
    B1 = "b1"
    B2 = "b2"
    C1 = "c1"
    C2 = "c2"


class Register(StrEnum):
    FORMAL = "formal"
    INFORMAL = "informal"
    SLANG = "slang"
    LITERARY = "literary"
    SPECIALIST = "specialist"


class MatchKind(StrEnum):
    EXACT = "exact"
    PREFIX = "prefix"
    SUBSTRING = "substring"
    FUZZY = "fuzzy"


class ReferenceSource(StrEnum):
    REFERENCE = "reference"
    WORDNET = "wordnet"


class HitKind(StrEnum):
    WORD = "word"
    REFERENCE = "reference"


INFLECTION_CODES = {
    "": Inflection.BASE,
    "p": Inflection.PAST,
    "pp": Inflection.PAST_PARTICIPLE,
    "3": Inflection.PRESENT_3SG,
    "ing": Inflection.ING,
    "pl": Inflection.PLURAL,
    "c": Inflection.COMPARATIVE,
    "s": Inflection.SUPERLATIVE,
}
SLOTS = frozenset(
    {
        "{sb}",
        "{sth}",
        "{one's}",
        "{oneself}",
        "{place}",
        "{doing}",
        "{do}",
        "{done}",
        "{adj}",
        "{adv}",
        "{num}",
        "{clause}",
    }
)


def normalize_pos(value: str | None) -> PartOfSpeech | None:
    """Interpret documented source labels without inventing a POS for an unknown label."""
    if not value:
        return None
    label = value.strip().lower()
    aliases = {
        "n": PartOfSpeech.NOUN,
        "v": PartOfSpeech.VERB,
        "a": PartOfSpeech.ADJECTIVE,
        "s": PartOfSpeech.ADJECTIVE,
        "r": PartOfSpeech.ADVERB,
        "adj": PartOfSpeech.ADJECTIVE,
        "adv": PartOfSpeech.ADVERB,
        "pron": PartOfSpeech.PRONOUN,
        "prep": PartOfSpeech.PREPOSITION,
        "conj": PartOfSpeech.CONJUNCTION,
        "det": PartOfSpeech.DETERMINER,
        "interj": PartOfSpeech.INTERJECTION,
        "num": PartOfSpeech.NUMERAL,
        "art": PartOfSpeech.ARTICLE,
        "aux": PartOfSpeech.AUXILIARY,
        "modal": PartOfSpeech.AUXILIARY,
    }
    try:
        return PartOfSpeech(label)
    except ValueError:
        return aliases.get(label.rstrip("."))
