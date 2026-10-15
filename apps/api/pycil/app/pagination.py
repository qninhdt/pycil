import base64
import binascii
import json
import math
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from fastapi import Request

from pycil.app.config import AppConfig
from pycil.app.http import Problem


def encode(
    binding: str | Mapping[str, object],
    seek: Sequence[object],
    *,
    as_of: datetime | str | None = None,
) -> str:
    body = {"v": 1, "binding": binding, "seek": seek, "as_of": as_of}
    return (
        base64.urlsafe_b64encode(
            json.dumps(
                body, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False
            ).encode()
        )
        .decode()
        .rstrip("=")
    )


def decode(
    token: str | None,
    binding: str | Mapping[str, object],
    types: Sequence[str],
    *,
    timed: bool = False,
) -> tuple[list[Any] | None, datetime | None]:
    if token is None:
        return None, None
    try:
        if not 1 <= len(token) <= 2048:
            raise ValueError()
        raw = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
        raw_json: object = json.loads(raw)
        if not isinstance(raw_json, dict):
            raise ValueError()
        data: dict[str, object] = cast(dict[str, object], raw_json)
        if (
            set(data.keys()) != {"v", "binding", "seek", "as_of"}
            or not isinstance(data["v"], int)
            or data["v"] != 1
            or data["binding"] != binding
        ):
            raise ValueError()
        seek_raw = data["seek"]
        if not isinstance(seek_raw, list):
            raise ValueError()
        seek_list: list[object] = cast(list[object], seek_raw)
        if len(seek_list) != len(types):
            raise ValueError()
        parsed: list[Any] = []
        for value, kind in zip(seek_list, types, strict=True):
            if kind == "nullable_time" and value is None:
                parsed.append(None)
                continue
            if kind in {"time", "nullable_time"}:
                if not isinstance(value, str):
                    raise ValueError()
                val_dt = datetime.fromisoformat(value)
                if val_dt.utcoffset() is None:
                    raise ValueError()
                parsed.append(val_dt)
            elif kind == "uuid":
                if not isinstance(value, str):
                    raise ValueError()
                parsed.append(UUID(value))
            elif kind == "id":
                if type(value) is not int or value <= 0:
                    raise ValueError()
                parsed.append(value)
            elif kind == "text":
                if not isinstance(value, str) or len(value) > 512:
                    raise ValueError()
                parsed.append(value)
            elif kind == "rank":
                if type(value) not in {int, float} or isinstance(value, bool):
                    raise ValueError()
                val_num = cast(int | float, value)
                if not 0 <= val_num < float("inf"):
                    raise ValueError()
                parsed.append(val_num)
            elif kind == "number":
                if type(value) not in {int, float} or isinstance(value, bool):
                    raise ValueError()
                val_num = cast(int | float, value)
                if not math.isfinite(val_num):
                    raise ValueError()
                parsed.append(val_num)
            else:
                parsed.append(value)
        as_of_val = data["as_of"]
        cutoff = datetime.fromisoformat(as_of_val) if timed and isinstance(as_of_val, str) else None
        if timed:
            if cutoff is None or cutoff.utcoffset() is None:
                raise ValueError()
        elif as_of_val is not None:
            raise ValueError()
        return parsed, cutoff
    except ValueError, TypeError, KeyError, binascii.Error, UnicodeDecodeError, RecursionError:
        raise Problem(422, "invalid_cursor") from None


def page_limit(limit: int | None, config: AppConfig) -> int:
    resolved: int = config.product.library.pagination.page_size if limit is None else limit
    if resolved < 1 or resolved > config.product.projections.max_page_size:
        raise Problem(422, "invalid_limit")
    return resolved


def includes(value: str | None, allowed: Collection[str]) -> set[str]:
    selected: set[str] = set(value.split(",")) if value else set()
    if not selected <= set(allowed):
        raise Problem(422, "invalid_include")
    return selected


def strict_query(request: Request, allowed: Collection[str]) -> None:
    query_keys = set(str(k) for k in request.query_params.keys())
    if query_keys - set(allowed) or any(
        len(request.query_params.getlist(key)) != 1 for key in query_keys
    ):
        raise Problem(422, "invalid_query_parameters")
