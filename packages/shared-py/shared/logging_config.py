"""Central structured-logging config shared by pycil-core and the worker.

Both processes use stdlib ``logging`` with ``logger.info(msg, extra={...})``
call sites. Without a formatter that knows about those keys, the ``extra``
fields are attached to the ``LogRecord`` and then silently dropped by the
default text formatter. ``JsonFormatter`` emits every non-standard record
attribute, so those fields actually reach stdout.

Stdlib only (no structlog) — zero new dependencies and zero call-site changes.
Idempotent: ``configure_logging`` rebuilds the root handler each call, so a
re-init (e.g. uvicorn reload, test re-entry) does not stack duplicate handlers.
"""
from __future__ import annotations

import json
import logging
import os

# Attributes present on a vanilla LogRecord. Anything on a record that is NOT
# in this set was passed via ``extra={}`` (or by an instrumentation library)
# and is what we want to surface as structured fields.
_RESERVED: frozenset[str] = frozenset(
    vars(logging.makeLogRecord({})).keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Render each record as a single-line JSON object including ``extra``."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = value if _json_safe(value) else repr(value)

        return json.dumps(payload, ensure_ascii=False, default=repr)


def _json_safe(value: object) -> bool:
    return isinstance(value, (str, int, float, bool, type(None), list, dict))


def configure_logging(*, service: str | None = None) -> None:
    """Install the JSON formatter on the root logger.

    Level comes from ``LOG_LEVEL`` (default INFO). ``LOG_FORMAT=text`` opts back
    into a human-readable line for local runs; anything else (or unset) uses
    JSON so ``extra={}`` fields serialize in deployed environments.
    """
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    use_text = os.getenv("LOG_FORMAT", "json").lower() == "text"

    if use_text:
        formatter: logging.Formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    else:
        formatter = JsonFormatter()

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    if service:
        handler.addFilter(_ServiceFilter(service))

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)


class _ServiceFilter(logging.Filter):
    """Stamp every record with the emitting service name."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self._service
        return True
