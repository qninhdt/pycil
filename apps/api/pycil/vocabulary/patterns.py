"""Bounded expression matching with explicit slots and licensed head inflections."""

import re
from collections.abc import Mapping, Sequence
from functools import lru_cache

from pycil.utils.strings import phrase_to_flexible_regex
from pycil.vocabulary.text import SLOT, answer_key, parse_marked_example, validate_lemma

WORD = r"[^\W_]+(?:['’-][^\W_]+)*"
BOUNDS = {
    "{sb}": (1, 4),
    "{sth}": (1, 5),
    "{one's}": (1, 2),
    "{oneself}": (1, 1),
    "{place}": (1, 4),
    "{doing}": (1, 4),
    "{do}": (1, 4),
    "{done}": (1, 4),
    "{adj}": (1, 4),
    "{adv}": (1, 4),
    "{num}": (1, 1),
    "{clause}": (2, 12),
}
SPECIAL = {
    "{sb}": (
        r"(?:someone|somebody|[a-z]+|(?:the|a|an|my|your|his|her|our|their)"
        r"\s+[a-z]+(?:\s+[a-z]+){0,2})"
    ),
    "{one's}": r"(?:my|your|his|her|its|our|their|one's|[a-z]+['’]s)",
    "{oneself}": r"(?:myself|yourself|himself|herself|itself|ourselves|themselves|oneself)",
    "{num}": r"(?:\d+(?:[.,]\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)",
}


def validate_pattern(value: str) -> str:
    if parse_marked_example(value)[1]:
        raise ValueError("patterns are plain text")
    value = validate_lemma(value)
    if re.search(r"\b[a-z]+/[a-z]+\b", value, re.I):
        raise ValueError("expand alternatives into distinct patterns")
    return value


@lru_cache(maxsize=1024)
def _parts(
    pattern: str, forms: tuple[tuple[str, tuple[str, ...]], ...]
) -> tuple[tuple[bool, tuple[re.Pattern[str], ...]], ...]:
    pieces: list[tuple[bool, tuple[re.Pattern[str], ...]]] = []
    cursor = 0
    for match in [*SLOT.finditer(pattern), None]:
        end = match.start() if match is not None else len(pattern)
        literal = pattern[cursor:end].casefold()
        variants = [literal]
        if cursor == 0 and literal.strip():
            head, separator, tail = literal.partition(" ")
            variants.extend(
                form + separator + tail for form in dict(forms).get(head, ()) if " " not in form
            )
        pieces.append(
            (False, tuple(re.compile(phrase_to_flexible_regex(v), re.I) for v in variants))
        )
        if match is not None:
            slot = match.group()
            minimum, maximum = BOUNDS[slot]
            expression = SPECIAL.get(slot, rf"{WORD}(?:\s+{WORD}){{{minimum - 1},{maximum - 1}}}")
            pieces.append((True, (re.compile(expression, re.I),)))
            cursor = match.end()
    return tuple(pieces)


def matches_pattern(
    pattern: str,
    surface: str,
    *,
    forms: Mapping[str, Sequence[str]] | None = None,
) -> bool:
    pattern = validate_pattern(pattern)
    if not surface.strip() or len(surface) > 256:
        return False
    surface = answer_key(surface)
    licensed: tuple[tuple[str, tuple[str, ...]], ...] = tuple(
        sorted(
            (head, tuple(answer_key(value) for value in values))
            for head, values in (forms or {}).items()
        )
    )
    positions: set[int] = {0}
    for slot, expressions in _parts(pattern, licensed):
        following: set[int] = set()
        for start in positions:
            for expression in expressions:
                if slot:
                    # Bounded states avoid exponential partitioning between adjacent slots.
                    following.update(
                        end
                        for end in range(start + 1, len(surface) + 1)
                        if expression.fullmatch(surface, start, end)
                    )
                elif match := expression.match(surface, start):
                    following.add(match.end())
        positions = following
        if not positions:
            return False
    return len(surface) in positions


def surface_head_key(value: str) -> str:
    return answer_key(value).partition(" ")[0].replace("ı", "i")


def pattern_head_key(value: str) -> str | None:
    value = validate_pattern(value)
    slot = SLOT.search(value)
    prefix = value[: slot.start()] if slot else value
    if not prefix.strip() or (slot and " " not in prefix):
        return None
    return surface_head_key(prefix)
