import pytest
import tantivy

from pycil.vocabulary import search
from pycil.vocabulary.enums import EntryType, MatchKind


def build(projection):
    index = tantivy.Index(search._schema())
    writer = index.writer(heap_size=15_000_000, num_threads=1)
    try:
        for document in search.SearchIndex.documents(projection, []):
            writer.add_document(document)
        writer.commit()
    finally:
        writer.wait_merging_threads()
    index.reload()
    return index


@pytest.mark.parametrize(
    ("query", "false_surface", "true_surface"),
    [
        ("abcd", "abc xbcd", "zabcd"),
        ("aaaaa", "aaaa", "zaaaaa"),
        ("CAFÉ", "caf autre afé", "zcafé"),
        ("cafe\u0301", "caf autre afé", "zcafé"),
        ("a.b", "aXb", "za.b"),
        ("bc", "bxc", "zbc"),
    ],
)
def test_substring_verifies_trigrams_and_pages_past_false_candidates(
    query, false_surface, true_surface
):
    index = build(
        (
            [(1, "alpha", EntryType.WORD), (2, "zulu", EntryType.WORD)],
            [(1, false_surface), (2, true_surface)],
            [],
            [],
            set(),
        )
    )
    hits = search.SearchIndex.find(index, query, False, 1)
    assert [(hit.word_id, hit.match_kind, hit.matched_surface) for hit in hits] == [
        (2, MatchKind.SUBSTRING, true_surface)
    ]


def test_pattern_pagination_preserves_ranking_and_stops_after_enough_matches(monkeypatch):
    words = [
        (identifier, f"entry{identifier:03d}", EntryType.EXPRESSION) for identifier in range(1, 101)
    ]
    patterns = [
        (
            identifier,
            identifier,
            "give {sb} a " + ("hammock" if identifier <= 40 else "hand"),
            "give",
        )
        for identifier in range(1, 101)
    ]
    index = build((words, [], [], patterns, set()))
    checked = []
    matches = search.matches_pattern

    def record(pattern, query, **kwargs):
        checked.append(pattern)
        return matches(pattern, query, **kwargs)

    monkeypatch.setattr(search, "matches_pattern", record)
    hits = search.SearchIndex.find(index, "give Jo a hand", False, 3)
    assert [(hit.word_id, hit.match_kind) for hit in hits] == [
        (identifier, MatchKind.EXACT) for identifier in [41, 42, 43]
    ]
    assert len(checked) == 43


def test_exact_results_do_not_construct_fallback_queries(monkeypatch):
    index = build(([(1, "bank", EntryType.WORD)], [], [], [], set()))

    def unexpected_fallback(*_args, **_kwargs):
        pytest.fail("a complete exact result must not construct fallback queries")

    monkeypatch.setattr(search.tantivy.Query, "regex_query", unexpected_fallback)
    monkeypatch.setattr(search.tantivy.Query, "fuzzy_term_query", unexpected_fallback)
    assert search.SearchIndex.find(index, "bank", False, 1)[0].word_id == 1


@pytest.mark.parametrize(
    ("pattern", "query"),
    [
        ("{sb} much", "Jo much"),
        ("{sth} inside {sth}", "book ınside box"),
        ("{sth} café", "book cafe\u0301"),
        ("{sth} a.b", "book a.b"),
        ("{sth} a", "book a"),
        ("{sth}", "book"),
        ("give {sb}", "give Jo"),
        ("give {sb} a hand", "gave Jo a hand"),
        ("give a hand", "gave a hand"),
    ],
)
def test_pattern_anchor_preserves_matching_and_filters_unrelated_patterns(
    monkeypatch, pattern, query
):
    words = [(1, "give", EntryType.EXPRESSION), (2, "unrelated", EntryType.EXPRESSION)]
    index = build(
        (
            words,
            [],
            [(1, 1, "gave")],
            [(1, 1, pattern, None), (2, 2, "{sth} unrelated", None)],
            set(),
        )
    )
    matches = search.matches_pattern
    checked = []

    def record(value, surface, **kwargs):
        checked.append(value)
        return matches(value, surface, **kwargs)

    monkeypatch.setattr(search, "matches_pattern", record)
    hits = search.SearchIndex.find(index, query, False, 20)
    assert any(hit.word_id == 1 and hit.match_kind is MatchKind.EXACT for hit in hits)
    assert checked == [pattern]


def test_single_character_query_does_not_scan_patterns_with_a_longer_required_tail(monkeypatch):
    index = build(
        (
            [(1, "a", EntryType.WORD), (2, "another", EntryType.EXPRESSION)],
            [],
            [],
            [(2, 2, "a much longer expression", "a"), (2, 2, "{sth} b", None)],
            set(),
        )
    )

    def unexpected_match(*_args, **_kwargs):
        pytest.fail("the required literal is absent from the query")

    monkeypatch.setattr(search, "matches_pattern", unexpected_match)
    assert search.SearchIndex.find(index, "a", False, 20)[0].word_id == 1
