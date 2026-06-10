"""Unit tests for `invoke_with_fallback` — the in-process fallback chain.

No network. `_invoke_one` is monkeypatched to a scripted fake so each test
controls exactly which model "succeeds" or "fails" and with what error class.
Pins the routing contract:
- first model succeeds → 0 hops, that model returned.
- retryable on model[0] → hop to model[1] → success at hop 1.
- terminal error → re-raise immediately, NO fallback, no further hops.
- every model retryable → OpenRouterAllModelsFailedError.
- empty chain → OpenRouterTerminalError (no_models_in_fallback_chain).
- whole-chain wall budget exceeded → OpenRouterAllModelsFailedError.
"""
from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from worker.llm import openrouter as orouter
from worker.llm.exceptions import (
    OpenRouterAllModelsFailedError,
    OpenRouterTerminalError,
)


class _Out(BaseModel):
    value: str


def _script(monkeypatch, behavior: dict[str, object]) -> list[str]:
    """Patch `_invoke_one` so each model maps to a result or raises.

    `behavior[model]` is either an `_Out` (return it) or an Exception
    instance (raise it). Records call order into the returned list.
    """
    calls: list[str] = []

    async def _fake(model: str, prompt: str, schema):  # noqa: ANN001
        calls.append(model)
        outcome = behavior[model]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(orouter, "_invoke_one", _fake)
    return calls


@pytest.mark.unit
async def test_first_model_succeeds_zero_hops(monkeypatch) -> None:
    calls = _script(monkeypatch, {"m0": _Out(value="ok")})
    result = await orouter.invoke_with_fallback("p", _Out, models=["m0", "m1"])
    assert result.model_used == "m0"
    assert result.hops == 0
    assert result.output.value == "ok"
    assert calls == ["m0"]  # m1 never touched


@pytest.mark.unit
async def test_retryable_hops_to_next_model(monkeypatch) -> None:
    calls = _script(
        monkeypatch,
        {
            "m0": _StatusRetryable(503),
            "m1": _Out(value="recovered"),
        },
    )
    result = await orouter.invoke_with_fallback("p", _Out, models=["m0", "m1"])
    assert result.model_used == "m1"
    assert result.hops == 1
    assert calls == ["m0", "m1"]


@pytest.mark.unit
async def test_terminal_error_no_fallback(monkeypatch) -> None:
    calls = _script(
        monkeypatch,
        {
            "m0": _StatusTerminal(400),
            "m1": _Out(value="should-never-run"),
        },
    )
    with pytest.raises(OpenRouterTerminalError):
        await orouter.invoke_with_fallback("p", _Out, models=["m0", "m1"])
    assert calls == ["m0"]  # terminal stops the chain dead


@pytest.mark.unit
async def test_all_models_retryable_raises_exhausted(monkeypatch) -> None:
    calls = _script(
        monkeypatch,
        {
            "m0": _StatusRetryable(429),
            "m1": _StatusRetryable(500),
            "m2": _StatusRetryable(503),
        },
    )
    with pytest.raises(OpenRouterAllModelsFailedError):
        await orouter.invoke_with_fallback("p", _Out, models=["m0", "m1", "m2"])
    assert calls == ["m0", "m1", "m2"]  # tried every model


@pytest.mark.unit
async def test_explicit_terminal_subclass_reraised(monkeypatch) -> None:
    # A raised OpenRouterTerminalError is caught by its own except arm and
    # re-raised verbatim (not reclassified).
    _script(monkeypatch, {"m0": OpenRouterTerminalError("bad schema")})
    with pytest.raises(OpenRouterTerminalError, match="bad schema"):
        await orouter.invoke_with_fallback("p", _Out, models=["m0"])


@pytest.mark.unit
async def test_empty_chain_is_terminal(monkeypatch) -> None:
    _script(monkeypatch, {})
    with pytest.raises(OpenRouterTerminalError, match="no_models_in_fallback_chain"):
        await orouter.invoke_with_fallback("p", _Out, models=[])


@pytest.mark.unit
async def test_budget_exceeded_raises_all_failed(monkeypatch) -> None:
    async def _slow(model: str, prompt: str, schema):  # noqa: ANN001
        await asyncio.sleep(0.2)
        return _Out(value="too-late")

    monkeypatch.setattr(orouter, "_invoke_one", _slow)
    with pytest.raises(OpenRouterAllModelsFailedError, match="chain_budget_exceeded"):
        await orouter.invoke_with_fallback(
            "p", _Out, models=["m0"], budget_seconds=0.01
        )


# --- helpers: status-carrying exceptions for classify_exception routing ---


class _StatusRetryable(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class _StatusTerminal(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code
