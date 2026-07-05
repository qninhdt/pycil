"""Question-format router: mastery cap never exceeded, valid lexi ids only."""

from pycil.learning.router_question import (
    CLOZE,
    CONTEXTUAL_MCQ,
    DEFINITION_MCQ,
    USE_IN_SENTENCE,
    choose_format,
)

_VALID = {DEFINITION_MCQ, CONTEXTUAL_MCQ, CLOZE, USE_IN_SENTENCE}
_MCQ = {DEFINITION_MCQ, CONTEXTUAL_MCQ}


def test_low_mastery_always_mcq():
    # mastery < 30 → cap 0 → only MCQ, and specifically definition_mcq.
    for i in range(50):
        fmt = choose_format(10, f"sense{i}:sess")
        assert fmt == DEFINITION_MCQ


def test_low_mastery_never_harder_than_mcq():
    for i in range(100):
        fmt = choose_format(0, f"s{i}")
        assert fmt in _MCQ


def test_mid_mastery_never_use_in_sentence():
    # 30-65 → cap 1 → cloze or mcq, NEVER use_in_sentence (harder than cap).
    seen = set()
    for i in range(200):
        fmt = choose_format(50, f"s{i}")
        assert fmt in _VALID
        assert fmt != USE_IN_SENTENCE
        seen.add(fmt)
    # Both cloze and mcq should appear across the distribution.
    assert CLOZE in seen


def test_high_mastery_can_use_any():
    seen = set()
    for i in range(300):
        fmt = choose_format(90, f"s{i}")
        assert fmt in _VALID
        seen.add(fmt)
    # High band allows the hardest format.
    assert USE_IN_SENTENCE in seen


def test_all_ids_are_valid_lexi_formats():
    for m in (0, 29, 30, 65, 66, 100):
        for i in range(20):
            assert choose_format(m, f"m{m}s{i}") in _VALID


def test_deterministic_for_same_seed():
    a = choose_format(50, "same:seed")
    b = choose_format(50, "same:seed")
    assert a == b


def test_boundary_65_is_mid_band():
    # 65 is inclusive upper bound of the mid band → never use_in_sentence.
    for i in range(100):
        assert choose_format(65, f"s{i}") != USE_IN_SENTENCE
