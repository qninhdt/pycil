from collections.abc import Collection, Mapping, Sequence
from datetime import datetime

from fastapi import Request

from pycil.app.config import AppConfig
from pycil.app.http import Problem
from pycil.utils.pagination import (
    CursorFieldType,
    InvalidCursorError,
    SeekValue,
    decode_cursor,
    encode_cursor,
)


def encode(
    binding: str | Mapping[str, object],
    seek: Sequence[object],
    *,
    as_of: datetime | str | None = None,
) -> str:
    return encode_cursor(binding, seek, as_of=as_of)


def decode(
    token: str | None,
    binding: str | Mapping[str, object],
    types: Sequence[CursorFieldType],
    *,
    timed: bool = False,
) -> tuple[list[SeekValue] | None, datetime | None]:
    try:
        return decode_cursor(token, binding, types, timed=timed)
    except InvalidCursorError:
        raise Problem(422, "invalid_cursor") from None


def page_limit(limit: int | None, config: AppConfig) -> int:
    resolved: int = config.library.page_size if limit is None else limit
    if resolved < 1 or resolved > config.library.max_page_size:
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
