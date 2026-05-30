"""LLM stub mode — return canned responses when WORKER_LLM_STUB=true.

When enabled, `invoke_with_fallback` returns a pre-canned response keyed
by the Pydantic schema class name, bypassing all OpenRouter calls.
Used by Playwright e2e tests to avoid external API costs.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_log = logging.getLogger(__name__)
_FIXTURE_PATH = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "llm_responses.json"


def _load_fixtures() -> dict[str, Any]:
    if not _FIXTURE_PATH.exists():
        _log.warning("llm_stub_fixture_not_found", extra={"path": str(_FIXTURE_PATH)})
        return {}
    with open(_FIXTURE_PATH) as f:
        return json.load(f)


def is_stub_mode() -> bool:
    return os.environ.get("WORKER_LLM_STUB", "").lower() in ("1", "true", "yes")


def get_stub_output(schema: type[BaseModel]) -> Any | None:
    if not is_stub_mode():
        return None
    fixtures = _load_fixtures()
    key = schema.__name__
    data = fixtures.get(key)
    if data is None:
        _log.warning("llm_stub_key_missing", extra={"key": key, "available": list(fixtures.keys())})
        return None
    return schema.model_validate(data)
