"""Coverage for llm_streaming.stream_chat (SSE chat token stream).

Pinned:
- Stub mode yields canned tokens + usage frame (no network).
- Missing api_key/model → single error frame.
- HTTP >=400 → error frame with status + truncated detail.
- Streaming assembly: skips non-data lines & bad JSON, yields tokens,
  stops at [DONE], surfaces usage frame.
- httpx.HTTPError mid-stream → network_error frame.
"""
from __future__ import annotations

import httpx
import pytest

from pycil_core.config import get_settings
from pycil_core.services import llm_streaming as svc


async def _drain(gen) -> list[dict]:
    return [frame async for frame in gen]


# --- Fake httpx streaming plumbing -----------------------------------------

class _FakeStreamResp:
    def __init__(self, *, status_code: int, lines: list[str], body: bytes = b""):
        self.status_code = status_code
        self._lines = lines
        self._body = body

    async def aread(self) -> bytes:
        return self._body

    async def aiter_lines(self):
        for ln in self._lines:
            yield ln


class _StreamCtx:
    def __init__(self, resp, raise_exc=None):
        self._resp = resp
        self._raise = raise_exc

    async def __aenter__(self):
        if self._raise is not None:
            raise self._raise
        return self._resp

    async def __aexit__(self, *a):
        return False


def _patch_stream(monkeypatch, resp=None, raise_exc=None):
    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, *a, **k):
            return _StreamCtx(resp, raise_exc=raise_exc)

    monkeypatch.setattr(svc.httpx, "AsyncClient", _Client)


def _configure(monkeypatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(s, "openrouter_chat_model", "test/chat")


# --- Stub mode --------------------------------------------------------------

async def test_stub_mode_yields_tokens_and_usage(monkeypatch):
    monkeypatch.setenv("LLM_STUB_MODE", "true")
    frames = await _drain(svc.stream_chat([{"role": "user", "content": "hi"}]))

    kinds = [f["kind"] for f in frames]
    assert kinds[-1] == "usage"
    assert all(k in ("token", "usage") for k in kinds)
    tokens = [f["token"] for f in frames if f["kind"] == "token"]
    assert "".join(tokens) == svc._CANNED_CHAT


# --- Config gate ------------------------------------------------------------

async def test_missing_config_yields_error(monkeypatch):
    monkeypatch.delenv("LLM_STUB_MODE", raising=False)
    s = get_settings()
    monkeypatch.setattr(s, "openrouter_api_key", None)
    monkeypatch.setattr(s, "openrouter_chat_model", None)
    monkeypatch.setattr(s, "openrouter_model", None)

    frames = await _drain(svc.stream_chat([{"role": "user", "content": "hi"}]))
    assert frames == [{"kind": "error", "error": "openrouter_not_configured"}]


# --- HTTP error -------------------------------------------------------------

async def test_http_error_status_yields_error_frame(monkeypatch):
    monkeypatch.delenv("LLM_STUB_MODE", raising=False)
    _configure(monkeypatch)
    resp = _FakeStreamResp(status_code=429, lines=[], body=b"rate limited" * 80)
    _patch_stream(monkeypatch, resp=resp)

    frames = await _drain(svc.stream_chat([{"role": "user", "content": "hi"}]))
    assert len(frames) == 1
    assert frames[0]["kind"] == "error"
    assert frames[0]["error"] == "openrouter_429"
    assert len(frames[0]["detail"]) <= 500


# --- Streaming assembly -----------------------------------------------------

async def test_stream_assembly_tokens_usage_and_done(monkeypatch):
    monkeypatch.delenv("LLM_STUB_MODE", raising=False)
    _configure(monkeypatch)
    lines = [
        "",  # blank skipped
        ": comment",  # non-data skipped
        'data: {"choices":[{"delta":{"content":"Hel"}}]}',
        'data: {"choices":[{"delta":{"content":"lo"}}]}',
        "data: not-json",  # bad JSON skipped
        'data: {"choices":[{"delta":{}}]}',  # empty delta → no token
        'data: {"usage":{"completion_tokens":2}}',
        "data: [DONE]",
        'data: {"choices":[{"delta":{"content":"AFTER"}}]}',  # never reached
    ]
    resp = _FakeStreamResp(status_code=200, lines=lines)
    _patch_stream(monkeypatch, resp=resp)

    frames = await _drain(svc.stream_chat([{"role": "user", "content": "hi"}]))
    tokens = [f["token"] for f in frames if f["kind"] == "token"]
    assert tokens == ["Hel", "lo"]  # AFTER not emitted (post-DONE)
    usage = [f for f in frames if f["kind"] == "usage"]
    assert usage and usage[0]["usage"]["completion_tokens"] == 2


async def test_network_error_midstream_yields_error_frame(monkeypatch):
    monkeypatch.delenv("LLM_STUB_MODE", raising=False)
    _configure(monkeypatch)
    _patch_stream(monkeypatch, raise_exc=httpx.ReadError("conn dropped"))

    frames = await _drain(svc.stream_chat([{"role": "user", "content": "hi"}]))
    assert len(frames) == 1
    assert frames[0]["kind"] == "error"
    assert frames[0]["error"] == "network_error"


@pytest.mark.parametrize(
    "val,expected",
    [("1", True), ("true", True), ("YES", True), ("", False), ("no", False)],
)
def test_is_stub_mode(monkeypatch, val, expected):
    monkeypatch.setenv("LLM_STUB_MODE", val)
    assert svc._is_stub_mode() is expected
