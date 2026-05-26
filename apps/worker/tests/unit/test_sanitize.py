"""Worker sanitize functions — pure logic, no I/O.

Pinned:
- `sanitize_text`: strips URLs, emails, HTML, control chars; collapses whitespace.
- `sanitize_answer`: keeps URLs/HTML (legitimate fill-in answers); strips only control chars.
- `sanitize_list` / `sanitize_answer_list`: drop empty results.
- Empty / None / whitespace-only inputs: return unchanged.
"""
from __future__ import annotations

import pytest

from worker.sanitize import (
    sanitize_answer,
    sanitize_answer_list,
    sanitize_list,
    sanitize_text,
)


@pytest.mark.parametrize(
    "input_, expected",
    [
        ("plain text", "plain text"),
        ("multi   space", "multi space"),
        ("hello https://x.com world", "hello world"),
        (
            "a https://x.com b https://y.io c",
            "a b c",
        ),
        ("contact me at foo@bar.com", "contact me at"),
        ("<b>bold</b> text", "bold text"),
        ("<b>hi</b> https://x.com\x00\x07", "hi"),
        ("control\x00chars\x1f", "controlchars"),
        ("", ""),
    ],
)
def test_sanitize_text_matrix(input_: str, expected: str) -> None:
    assert sanitize_text(input_) == expected


def test_sanitize_text_none_returns_none() -> None:
    assert sanitize_text(None) is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "input_, expected",
    [
        ("answer", "answer"),
        ("https://example.com/answer", "https://example.com/answer"),
        ("<b>answer</b>", "<b>answer</b>"),
        ("contains\x00control", "containscontrol"),
        ("multi   spaces", "multi spaces"),
        ("", ""),
    ],
)
def test_sanitize_answer_keeps_urls_and_html(input_: str, expected: str) -> None:
    assert sanitize_answer(input_) == expected


def test_sanitize_list_drops_empties() -> None:
    out = sanitize_list(["alpha", "https://only", "  ", "beta"])
    assert "alpha" in out and "beta" in out
    assert "https://only" not in out
    # Whitespace-only collapses to "" then filtered.
    assert "" not in out
    assert "  " not in out


def test_sanitize_answer_list_keeps_urls() -> None:
    out = sanitize_answer_list(["alpha", "https://x.com"])
    assert out == ["alpha", "https://x.com"]
