"""Pycil foundation utilities package."""

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
from pycil.utils.pagination import (
    CursorFieldType,
    InvalidCursorError,
    SeekValue,
    decode_cursor,
    encode_cursor,
)
from pycil.utils.schemas import PositiveID, PositiveInt, Strict, StrictModel
from pycil.utils.strings import (
    has_control_or_invisible_chars,
    ngrams,
    normalize_nfkc_whitespace,
    phrase_to_flexible_regex,
    slugify,
    strip_accents,
)

__all__ = [
    "CursorFieldType",
    "InvalidCursorError",
    "PositiveID",
    "PositiveInt",
    "SeekValue",
    "Strict",
    "StrictModel",
    "base64url_decode",
    "base64url_encode",
    "date_range",
    "decode_cursor",
    "encode_cursor",
    "has_control_or_invisible_chars",
    "http_status_phrase",
    "is_transient_http_status",
    "ngrams",
    "normalize_http_method",
    "normalize_nfkc_whitespace",
    "period_bounds",
    "phrase_to_flexible_regex",
    "resolve_date_window",
    "row_data",
    "sha256_canonical_json",
    "sha256_hex",
    "shielded_to_thread",
    "slugify",
    "strip_accents",
    "to_local_date",
    "utc_now",
]
