"""Unit tests for `_invoke_one` — the structured-output parse/validate seam.

No network. `_client` is monkeypatched to a fake ChatOpenAI whose
`with_structured_output(...).ainvoke(...)` yields a scripted raw value.
Pins the contract `_invoke_one` enforces on top of LangChain:
- raw already a schema instance → returned as-is.
- raw a dict → coerced via `schema.model_validate`.
- raw a dict that violates the schema → pydantic ValidationError propagates
  (so the caller's classify_exception can route it to terminal).
- `with_structured_output` is asked for `method="json_mode"` with the schema.
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel, Field, ValidationError

from worker.llm import openrouter as orouter


class _Out(BaseModel):
    value: str = Field(min_length=1)
    count: int


class _FakeStructured:
    def __init__(self, raw: object) -> None:
        self._raw = raw

    async def ainvoke(self, prompt: object) -> object:  # noqa: ANN401
        return self._raw


class _FakeClient:
    """Stands in for ChatOpenAI; records the structured-output request."""

    def __init__(self, raw: object) -> None:
        self._raw = raw
        self.requested: dict[str, object] = {}

    def with_structured_output(self, schema: type, *, method: str):  # noqa: ANN001
        self.requested = {"schema": schema, "method": method}
        return _FakeStructured(self._raw)


def _patch_client(monkeypatch, raw: object) -> _FakeClient:
    fake = _FakeClient(raw)
    monkeypatch.setattr(orouter, "_client", lambda model=None: fake)
    return fake


@pytest.mark.unit
async def test_returns_instance_unchanged(monkeypatch) -> None:
    instance = _Out(value="hi", count=3)
    _patch_client(monkeypatch, instance)
    result = await orouter._invoke_one("m0", "p", _Out)
    assert result is instance


@pytest.mark.unit
async def test_dict_is_validated_into_schema(monkeypatch) -> None:
    _patch_client(monkeypatch, {"value": "hi", "count": 7})
    result = await orouter._invoke_one("m0", "p", _Out)
    assert isinstance(result, _Out)
    assert result.value == "hi"
    assert result.count == 7


@pytest.mark.unit
async def test_invalid_dict_raises_validation_error(monkeypatch) -> None:
    # Missing required `count`, empty `value` — model_validate must reject.
    _patch_client(monkeypatch, {"value": ""})
    with pytest.raises(ValidationError):
        await orouter._invoke_one("m0", "p", _Out)


@pytest.mark.unit
async def test_requests_json_mode_with_schema(monkeypatch) -> None:
    fake = _patch_client(monkeypatch, _Out(value="x", count=1))
    await orouter._invoke_one("m0", "p", _Out)
    assert fake.requested == {"schema": _Out, "method": "json_mode"}
