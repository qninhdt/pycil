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
        (identifier, identifier, "give {sb} a " + ("book" if identifier <= 40 else "hand"), "give")
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
