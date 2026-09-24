"""Structural boundaries for data returned to the assistant model."""

from collections.abc import Mapping
from typing import Any

EXTERNAL_DATA_KEY = "__pycil_external_data__"


def wrap_external(value: str) -> dict[str, str]:
    """Represent an untrusted string as data rather than prompt text."""
    return {EXTERNAL_DATA_KEY: value}


def wrap_external_strings(value: Any) -> Any:
    """Recursively wrap external string values without delimiter-based escaping."""
    if isinstance(value, str):
        return wrap_external(value)
    if isinstance(value, Mapping):
        return {key: wrap_external_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [wrap_external_strings(item) for item in value]
    if isinstance(value, tuple):
        return [wrap_external_strings(item) for item in value]
    return value
