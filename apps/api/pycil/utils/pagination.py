"""Seek-based pagination token serialization and validation (RFC 4648 / JSON)."""

import binascii
import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from pycil.utils.encoding import base64url_decode, base64url_encode

type CursorFieldType = Literal[
    "nullable_time",
    "time",
    "uuid",
    "id",
    "text",
    "rank",
    "number",
]

type SeekValue = datetime | UUID | int | float | str | None


class InvalidCursorError(ValueError):
    """Raised when a pagination cursor token is malformed, invalid, or expired."""


def encode_cursor(
    binding: str | Mapping[str, object],
    seek: Sequence[object],
    *,
    as_of: datetime | str | None = None,
) -> str:
    """Encode pagination seek parameters into an unpadded base64url JSON token."""
    body = {"v": 1, "binding": binding, "seek": seek, "as_of": as_of}
    payload = json.dumps(
        body, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False
    ).encode()
    return base64url_encode(payload)


def decode_cursor(
    token: str | None,
    binding: str | Mapping[str, object],
    types: Sequence[CursorFieldType],
    *,
    timed: bool = False,
) -> tuple[list[SeekValue] | None, datetime | None]:
    """Decode and validate a seek pagination token against expected type signatures."""
    if token is None:
        return None, None
    try:
        if not 1 <= len(token) <= 2048:
            raise InvalidCursorError("token length out of bounds")
        raw = base64url_decode(token)
        raw_json = json.loads(raw)
        if not isinstance(raw_json, dict):
            raise InvalidCursorError("token body is not a JSON object")
        data = cast(dict[str, object], raw_json)
        if (
            set(data.keys()) != {"v", "binding", "seek", "as_of"}
            or not isinstance(data["v"], int)
            or data["v"] != 1
            or data["binding"] != binding
        ):
            raise InvalidCursorError("invalid token schema or binding mismatch")
        seek_raw = data["seek"]
        if not isinstance(seek_raw, list):
            raise InvalidCursorError("seek must be a list")
        seek_list = cast(list[object], seek_raw)
        if len(seek_list) != len(types):
            raise InvalidCursorError("seek list length does not match types")
        parsed: list[SeekValue] = []
        for value, kind in zip(seek_list, types, strict=True):
            if kind == "nullable_time" and value is None:
                parsed.append(None)
                continue
            if kind in {"time", "nullable_time"}:
                if not isinstance(value, str):
                    raise InvalidCursorError("time seek value must be str")
                val_dt = datetime.fromisoformat(value)
                if val_dt.utcoffset() is None:
                    raise InvalidCursorError("time seek value must be timezone-aware")
                parsed.append(val_dt)
            elif kind == "uuid":
                if not isinstance(value, str):
                    raise InvalidCursorError("uuid seek value must be str")
                parsed.append(UUID(value))
            elif kind == "id":
                if type(value) is not int or value <= 0:
                    raise InvalidCursorError("id seek value must be positive int")
                parsed.append(value)
            elif kind == "text":
                if not isinstance(value, str) or len(value) > 512:
                    raise InvalidCursorError("text seek value must be str <= 512 chars")
                parsed.append(value)
            elif kind == "rank":
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise InvalidCursorError("rank seek value must be a number")
                if not 0 <= value < float("inf"):
                    raise InvalidCursorError("rank seek value must be non-negative finite")
                parsed.append(value)
            elif kind == "number":
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise InvalidCursorError("number seek value must be a number")
                if not math.isfinite(value):
                    raise InvalidCursorError("number seek value must be finite")
                parsed.append(value)
            else:
                raise InvalidCursorError(f"unknown seek kind: {kind}")
        as_of_val = data["as_of"]
        cutoff = datetime.fromisoformat(as_of_val) if timed and isinstance(as_of_val, str) else None
        if timed:
            if cutoff is None or cutoff.utcoffset() is None:
                raise InvalidCursorError("timed cursor requires timezone-aware as_of")
        elif as_of_val is not None:
            raise InvalidCursorError("untimed cursor cannot have as_of")
        return parsed, cutoff
    except (
        ValueError,
        TypeError,
        KeyError,
        binascii.Error,
        UnicodeDecodeError,
        RecursionError,
    ) as exc:
        if isinstance(exc, InvalidCursorError):
            raise
        raise InvalidCursorError(f"malformed cursor: {exc}") from exc
