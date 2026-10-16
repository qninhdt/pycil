from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from pycil.utils.concurrency import shielded_to_thread
from pycil.utils.dates import (
    date_range,
    period_bounds,
    resolve_date_window,
    to_local_date,
    utc_now,
)
from pycil.utils.encoding import base64url_decode, base64url_encode
from pycil.utils.hashing import sha256_canonical_json, sha256_hex
from pycil.utils.http import http_status_phrase, is_transient_http_status, normalize_http_method
from pycil.utils.orm import row_data
from pycil.utils.pagination import InvalidCursorError, decode_cursor, encode_cursor
from pycil.utils.schemas import PositiveID, Strict
from pycil.utils.strings import (
    has_control_or_invisible_chars,
    ngrams,
    normalize_nfkc_whitespace,
    phrase_to_flexible_regex,
    slugify,
    strip_accents,
)


def test_encoding_roundtrip():
    data = b"hello \x00\xff world!?"
    token = base64url_encode(data)
    assert "=" not in token
    assert base64url_decode(token) == data


def test_hashing():
    assert sha256_hex("test") == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
    assert sha256_hex(b"test") == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"

    dict1 = {"b": 2, "a": 1}
    dict2 = {"a": 1, "b": 2}
    assert sha256_canonical_json(dict1) == sha256_canonical_json(dict2)


def test_strings():
    # Accent stripping
    assert strip_accents("Nguyễn Đắc Ninh") == "Nguyen Dac Ninh"
    assert strip_accents("Đà Nẵng") == "Da Nang"

    # Slugify
    assert slugify("Nguyễn Đắc Ninh") == "nguyen_dac_ninh"
    assert slugify("Hello, World! 123", delimiter="-") == "hello-world-123"

    # NFKC & whitespace
    assert normalize_nfkc_whitespace("  hello   \t\n world  ") == "hello world"

    # Control chars
    assert has_control_or_invisible_chars("hello\x00world") is True
    assert has_control_or_invisible_chars("clean text") is False

    # Ngrams
    assert ngrams("apple", 3) == {"app", "ppl", "ple"}
    assert ngrams("hi", 3) == set()

    # Regex
    pattern = phrase_to_flexible_regex("take off")
    assert r"\s+" in pattern


def test_dates():
    now = utc_now()
    assert now.tzinfo is UTC

    local_d = to_local_date(datetime(2026, 1, 1, 23, 0, tzinfo=UTC), "Asia/Ho_Chi_Minh")
    assert local_d == date(2026, 1, 2)

    days = list(date_range(date(2026, 1, 1), date(2026, 1, 3)))
    assert days == [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]

    # Period bounds
    anchor = datetime(2026, 1, 15, 0, 0, tzinfo=UTC)
    moment = datetime(2026, 2, 20, 0, 0, tzinfo=UTC)
    start, end = period_bounds(anchor, moment)
    assert start == datetime(2026, 2, 15, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 3, 15, 0, 0, tzinfo=UTC)

    # Date window
    today = date(2026, 5, 10)
    w_start, w_end = resolve_date_window(None, None, today, 7)
    assert w_end == today
    assert w_start == today - timedelta(days=6)

    with pytest.raises(ValueError):
        resolve_date_window(date(2026, 5, 1), None, today, 7)


def test_pagination():
    token = encode_cursor("test_binding", ["2026-01-01T00:00:00Z", 42])
    seek, as_of = decode_cursor(token, "test_binding", ["time", "id"])
    assert as_of is None
    assert seek is not None
    assert seek[0] == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    assert seek[1] == 42

    with pytest.raises(InvalidCursorError):
        decode_cursor("invalid_base64!", "test_binding", ["id"])

    with pytest.raises(InvalidCursorError):
        decode_cursor(token, "different_binding", ["time", "id"])


def test_http():
    assert http_status_phrase(200) == "OK"
    assert http_status_phrase(404) == "Not Found"
    assert http_status_phrase(999) == "Error"

    assert normalize_http_method("GET") == "GET"
    assert normalize_http_method("post") == "_OTHER"
    assert normalize_http_method("INVALID") == "_OTHER"

    assert is_transient_http_status(429) is True
    assert is_transient_http_status(503) is True
    assert is_transient_http_status(404) is False
    assert is_transient_http_status(None) is False


def test_schemas():
    class Item(Strict):
        id: PositiveID

    item = Item(id=5)
    assert item.id == 5

    with pytest.raises(ValidationError):
        Item(id=-1)

    with pytest.raises(ValidationError):
        Item(id=5, extra="not allowed")


async def test_shielded_to_thread():
    def compute(x: int) -> int:
        return x * 2

    assert await shielded_to_thread(lambda: compute(21)) == 42


def test_row_data():
    class FakeColumn:
        def __init__(self, name: str, computed: object = None):
            self.name = name
            self.computed = computed

    class FakeTable:
        columns = [
            FakeColumn("id"),
            FakeColumn("name"),
            FakeColumn("generated_col", computed="SOMETHING"),
        ]

    from types import SimpleNamespace

    row = SimpleNamespace(__table__=FakeTable(), id=10, name="sample", generated_col="computed_val")
    assert row_data(row) == {"id": 10, "name": "sample"}
