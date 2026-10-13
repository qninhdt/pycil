from types import SimpleNamespace

import pytest

from pycil.vocabulary.enums import Inflection
from pycil.vocabulary.errors import InvalidOutputError
from pycil.vocabulary.patterns import matches_pattern, validate_pattern
from pycil.vocabulary.text import (
    canonical_markup,
    content_hash,
    marked_occurrences,
    match_key,
    parse_form,
    parse_marked_example,
    target_sequences,
    validate_lemma,
)


def test_identity_normalizes_unicode_case_and_spaces_without_normalizing_translation_text():
    assert validate_lemma("  Ｂank   account ") == "Bank account"
    assert match_key("Straße") == match_key("STRASSE")
    assert validate_lemma("give {sb} {sth}") == "give {sb} {sth}"
    assert content_hash("bank") != content_hash("Bank") != content_hash(" bank")


@pytest.mark.parametrize(
    "value",
    ["", "a\nb", "a\u200bb", "{unknown}", "give {sb", "word}", "bank(s)", "bank etc.", "x" * 257],
)
def test_invalid_identity_is_rejected(value):
    with pytest.raises(ValueError):
        validate_lemma(value)


@pytest.mark.parametrize(
    "notation, surface, inf",
    [
        ("bank", "bank", Inflection.BASE),
        ("banks|PL", "banks", Inflection.PLURAL),
        ("ran|p", "ran", Inflection.PAST),
        ("run|pp", "run", Inflection.PAST_PARTICIPLE),
        ("runs|3", "runs", Inflection.PRESENT_3SG),
        ("running|ing", "running", Inflection.ING),
        ("better|c", "better", Inflection.COMPARATIVE),
        ("best|s", "best", Inflection.SUPERLATIVE),
    ],
)
def test_form_notation_preserves_surface_and_decodes_inflection(notation, surface, inf):
    assert parse_form(notation) == (surface, inf)


@pytest.mark.parametrize("value", ["bank|", "bank|unknown", "bank|pl|p", "[bank]", "|p"])
def test_invalid_form_notation(value):
    with pytest.raises(ValueError):
        parse_form(value)


def test_markup_offsets_and_canonical_codes():
    plain, spans = parse_marked_example("é [banks|PL] and [bank].")
    assert plain == "é banks and bank."
    assert [(s.surface, s.inf, s.start, s.end) for s in spans] == [
        ("banks", Inflection.PLURAL, 2, 7),
        ("bank", Inflection.BASE, 12, 16),
    ]
    assert all(plain[s.start : s.end] == s.surface for s in spans)
    assert canonical_markup("[banks|PL]") == "[banks|pl]"
    assert parse_marked_example("plain text") == ("plain text", [])


@pytest.mark.parametrize(
    "value", ["[bank", "bank]", "[[bank]]", "[ ]", "[bank|bad]", "[bank|pl|p]"]
)
def test_invalid_markup(value):
    with pytest.raises(ValueError):
        parse_marked_example(value)


def test_expression_target_requires_all_fixed_components_and_counts_repetitions():
    word = SimpleNamespace(lemma="give {sb} a hand", aliases=["help out"])
    sense = SimpleNamespace(forms=[SimpleNamespace(surface="gave")])
    sequences = target_sequences(word, sense)
    assert marked_occurrences("I [gave] Jo [a hand] and [help out] today.", sequences) == 2
    for text in ["I [gave] Jo a hand.", "I [gave] Jo [the hand].", "No tags."]:
        with pytest.raises(InvalidOutputError):
            marked_occurrences(text, sequences)
    assert marked_occurrences("No tags.", sequences, required=False) == 0


@pytest.mark.parametrize(
    "pattern, good, bad",
    [
        ("give {sb} a hand", "give my friend a hand", "give a hand"),
        ("lose {one's} temper", "lose her temper", "lose herself temper"),
        ("enjoy {oneself}", "enjoy yourself", "enjoy your friend"),
        ("count {num} sheep", "count 12 sheep", "count many sheep"),
        ("say {clause}", "say we are ready", "say yes"),
    ],
)
def test_bounded_slots_match_whole_surface(pattern, good, bad):
    assert matches_pattern(pattern, good)
    assert not matches_pattern(pattern, bad)
    assert not matches_pattern(pattern, "unrelated " + good)


def test_only_licensed_head_forms_are_matched():
    assert matches_pattern("give {sb} a hand", "gave Jo a hand", forms={"give": ["gave"]})
    assert not matches_pattern("give {sb} a hand", "gave Jo a hand")
    assert not matches_pattern("give {sth}", "give " + " ".join(["thing"] * 6))


@pytest.mark.parametrize("pattern", ["[bank]", "bank(s)", "give/take {sth}", "give {unknown}"])
def test_patterns_require_expanded_plain_expressions(pattern):
    with pytest.raises(ValueError):
        validate_pattern(pattern)
