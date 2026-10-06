"""Validated opaque seek tokens, never permission grants or database anchor lookups."""

import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from pycil.http import Problem


def encode(binding, seek, *, as_of=None):
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


def decode(token, binding, types, *, timed=False):
    if token is None:
        return None, None
    try:
        if not isinstance(token, str) or not 1 <= len(token) <= 2048:
            raise ValueError()
        data = json.loads(
            base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
        )
        if (
            set(data) != {"v", "binding", "seek", "as_of"}
            or type(data["v"]) is not int
            or data["v"] != 1
            or data["binding"] != binding
        ):
            raise ValueError()
        if not isinstance(data["seek"], list) or len(data["seek"]) != len(types):
            raise ValueError()
        parsed = []
        for value, kind in zip(data["seek"], types, strict=True):
            if kind == "nullable_time" and value is None:
                parsed.append(None)
                continue
            if kind in {"time", "nullable_time"}:
                value = datetime.fromisoformat(value)
                if value.utcoffset() is None:
                    raise ValueError()
            elif kind == "uuid":
                if not isinstance(value, str):
                    raise ValueError()
                value = UUID(value)
            elif kind == "id":
                if type(value) is not int or value <= 0:
                    raise ValueError()
            elif kind == "text":
                if not isinstance(value, str) or len(value) > 512:
                    raise ValueError()
            elif kind == "rank":
                if type(value) not in {int, float} or not 0 <= value < float("inf"):
                    raise ValueError()
            parsed.append(value)
        cutoff = datetime.fromisoformat(data["as_of"]) if timed else None
        if timed and cutoff.utcoffset() is None or not timed and data["as_of"] is not None:
            raise ValueError()
        return parsed, cutoff
    except ValueError, TypeError, KeyError, binascii.Error, UnicodeDecodeError, RecursionError:
        raise Problem(422, "invalid_cursor") from None


def page_limit(limit, config):
    limit = config.library.page_size if limit is None else limit
    if type(limit) is not int or not 1 <= limit <= config.projections.max_page_size:
        raise Problem(422, "invalid_limit")
    return limit


def includes(value, allowed):
    selected = set(value.split(",")) if value else set()
    if not selected <= allowed:
        raise Problem(422, "invalid_include")
    return selected


def strict_query(request, allowed):
    if set(request.query_params) - set(allowed) or any(
        len(request.query_params.getlist(key)) != 1 for key in request.query_params
    ):
        raise Problem(422, "invalid_query_parameters")
