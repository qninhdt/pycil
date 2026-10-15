"""Lexical identity, exact translation keys and explicit target markup."""

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from pycil.vocabulary.enums import INFLECTION_CODES, SLOTS, Inflection
from pycil.vocabulary.errors import InvalidOutputError


class HasSurface(Protocol):
    @property
    def surface(self) -> str: ...


class WordLike(Protocol):
    @property
    def lemma(self) -> str: ...
    @property
    def aliases(self) -> Sequence[str]: ...


class SenseLike(Protocol):
    @property
    def forms(self) -> Iterable[HasSurface]: ...


MAX_LEMMA_LENGTH = 256
MAX_TEXT_LENGTH = 16000
SLOT = re.compile(r"\{[^{}]*\}")
TAG = re.compile(r"\[([^\[\]|]+)(?:\|([a-z0-9]+))?\]", re.I)


def validate_lemma(value: str) -> str:
    if not value.strip() or len(value) > MAX_LEMMA_LENGTH:
        raise ValueError("invalid lemma length")
    if any(ord(char) < 32 or unicodedata.category(char) == "Cf" for char in value):
        raise ValueError("invisible/control character in lemma")
    remaining = SLOT.sub("", value)
    if (
        "{" in remaining
        or "}" in remaining
        or any(m.group() not in SLOTS for m in SLOT.finditer(value))
    ):
        raise ValueError("unknown or malformed expression slot")
    if "(" in value or ")" in value or re.search(r"\betc\.(?:\s|$)", value, re.I):
        raise ValueError("citation includes optional/alternative notation")
    return " ".join(unicodedata.normalize("NFKC", value).split())


def match_key(value: str) -> str:
    return validate_lemma(value).casefold()


def answer_key(value: str) -> str:
    if not value.strip() or len(value) > MAX_TEXT_LENGTH:
        raise ValueError("invalid answer")
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def content_hash(value: str) -> str:
    if not value or len(value) > MAX_TEXT_LENGTH:
        raise ValueError("invalid translation input")
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class Span:
    surface: str
    inf: Inflection
    start: int
    end: int


def parse_marked_example(value: str) -> tuple[str, list[Span]]:
    if len(value) > MAX_TEXT_LENGTH:
        raise ValueError("invalid marked text")
    chunks: list[str] = []
    spans: list[Span] = []
    cursor = length = 0
    for tag in TAG.finditer(value):
        before = value[cursor : tag.start()]
        surface, code = tag.groups()
        if "[" in before or "]" in before or not surface.strip():
            raise ValueError("invalid target markup")
        if (code or "").lower() not in INFLECTION_CODES:
            raise ValueError("unknown target inflection")
        length += len(before)
        spans.append(
            Span(surface, INFLECTION_CODES[(code or "").lower()], length, length + len(surface))
        )
        chunks.extend((before, surface))
        length += len(surface)
        cursor = tag.end()
    tail = value[cursor:]
    if "[" in tail or "]" in tail:
        raise ValueError("invalid target markup")
    return "".join([*chunks, tail]), spans


def strip_markup(value: str) -> str:
    return parse_marked_example(value)[0]


def canonical_markup(value: str) -> str:
    parse_marked_example(value)
    return TAG.sub(lambda tag: "[" + tag[1] + ("|" + tag[2].lower() if tag[2] else "") + "]", value)


def parse_form(value: str) -> tuple[str, Inflection]:
    surface, separator, code = value.partition("|")
    if any(char in surface for char in "[]|") or code.lower() not in INFLECTION_CODES:
        raise ValueError("invalid form notation")
    if separator and not code:
        raise ValueError("missing inflection code")
    return validate_lemma(surface), INFLECTION_CODES[code.lower()]


def components(surface: str) -> tuple[str, ...]:
    return tuple(answer_key(SLOT.sub(" ", surface)).split())


def target_sequences(word: WordLike, sense: SenseLike) -> set[tuple[str, ...]]:
    sequences = {components(surface) for surface in [word.lemma, *word.aliases]}
    base = components(word.lemma)
    for form in sense.forms:
        tokens = components(form.surface)
        sequences.add(tokens if len(base) == 1 or len(tokens) > 1 else tokens + base[1:])
    return sequences


def marked_occurrences(
    text: str, sequences: Iterable[tuple[str, ...]], required: bool = True
) -> int:
    _plain, spans = parse_marked_example(text)
    if not spans and required:
        raise InvalidOutputError("target is not marked")
    tokens = tuple(token for span in spans for token in answer_key(span.surface).split())
    positions: dict[int, int] = {0: 0}
    for start in range(len(tokens)):
        if start not in positions:
            continue
        for sequence in sequences:
            if sequence and tokens[start : start + len(sequence)] == sequence:
                end = start + len(sequence)
                positions[end] = min(positions.get(end, len(tokens)), positions[start] + 1)
    if len(tokens) not in positions:
        raise InvalidOutputError("target tags omit or add fixed lexical components")
    return positions[len(tokens)]
