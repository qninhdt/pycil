"""The shared JSON log formatter must serialize ``extra={}`` fields.

Regression guard: the prior text formatter attached ``extra`` keys to the
LogRecord and then dropped them, so "structured" spend/config lines were
plain text in practice. These tests pin that the JSON formatter actually
emits those fields.
"""
from __future__ import annotations

import json
import logging

import pytest
from shared.logging_config import JsonFormatter, configure_logging


@pytest.mark.unit
def test_extra_fields_appear_in_json_output() -> None:
    record = logging.LogRecord(
        name="worker.spend",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="spend",
        args=(),
        exc_info=None,
    )
    record.job_id = "j-123"
    record.cost_usd = 0.0042

    payload = json.loads(JsonFormatter().format(record))

    assert payload["msg"] == "spend"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "worker.spend"
    assert payload["job_id"] == "j-123"
    assert payload["cost_usd"] == 0.0042


@pytest.mark.unit
def test_non_json_safe_value_is_stringified() -> None:
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="m",
        args=(),
        exc_info=None,
    )
    record.obj = object()  # not JSON-serializable

    payload = json.loads(JsonFormatter().format(record))
    assert isinstance(payload["obj"], str)


@pytest.mark.unit
def test_configure_logging_is_idempotent() -> None:
    configure_logging(service="t")
    configure_logging(service="t")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)


@pytest.mark.unit
def test_text_format_opt_out(monkeypatch) -> None:
    monkeypatch.setenv("LOG_FORMAT", "text")
    configure_logging()
    root = logging.getLogger()
    assert not isinstance(root.handlers[0].formatter, JsonFormatter)
    # Reset to JSON so later tests/processes are unaffected.
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    configure_logging()
