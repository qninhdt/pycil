"""Coverage for llm_judge_service (tier-4 LLM grader).

Pinned:
- Disabled / no-key → "incorrect" with zero LLM call.
- Cache hit short-circuits.
- Per-user daily limit + global budget caps return "incorrect".
- Success path parses verdict, caches it, books spend.
- Transport / parse failure degrades to "incorrect".
"""
from __future__ import annotations

import httpx
import pytest

from pycil_core.config import get_settings
from pycil_core.services import llm_judge_service as svc


def _enable(monkeypatch, **over) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "llm_judge_enabled", True)
    monkeypatch.setattr(s, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(s, "llm_judge_per_user_daily_limit", 50)
    monkeypatch.setattr(s, "llm_judge_budget_daily_usd", 1.0)
    monkeypatch.setattr(s, "llm_judge_model", "test/model")
    for k, v in over.items():
        monkeypatch.setattr(s, k, v)


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._p = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._p


def _patch_client(monkeypatch, *, content="yes", raise_exc=None):
    class _Client:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            if raise_exc is not None:
                raise raise_exc
            return _Resp({"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(svc.httpx, "AsyncClient", _Client)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("yes", "correct"),
        ("Yes.", "correct"),
        ("borderline", "borderline"),
        ("no", "incorrect"),
        ("garbage words", "incorrect"),
        ("", "incorrect"),
    ],
)
def test_parse_response_tiers(text: str, expected: str) -> None:
    assert svc._parse_response(text) == expected


async def test_disabled_returns_incorrect_no_call(fakeredis_client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_judge_enabled", False)

    def _boom(*a, **k):  # any HTTP attempt = test failure
        raise AssertionError("must not call OpenRouter when disabled")

    monkeypatch.setattr(svc.httpx, "AsyncClient", _boom)

    out = await svc.judge(
        redis=fakeredis_client,
        user_id=1,
        definition_id=10,
        canonical="a feline",
        user_answer="cat",
        normalized="cat",
    )
    assert out == "incorrect"


async def test_no_api_key_returns_incorrect(fakeredis_client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_judge_enabled", True)
    monkeypatch.setattr(s, "openrouter_api_key", None)

    out = await svc.judge(
        redis=fakeredis_client,
        user_id=1,
        definition_id=10,
        canonical="a feline",
        user_answer="cat",
        normalized="cat",
    )
    assert out == "incorrect"


async def test_cache_hit_short_circuits(fakeredis_client, monkeypatch):
    _enable(monkeypatch)
    key = svc._cache_key(10, "cat")
    await fakeredis_client.set(key, "borderline")

    def _boom(*a, **k):
        raise AssertionError("cache hit must not call OpenRouter")

    monkeypatch.setattr(svc.httpx, "AsyncClient", _boom)

    out = await svc.judge(
        redis=fakeredis_client,
        user_id=1,
        definition_id=10,
        canonical="a feline",
        user_answer="cat",
        normalized="cat",
    )
    assert out == "borderline"


async def test_per_user_limit_returns_incorrect(fakeredis_client, monkeypatch):
    _enable(monkeypatch, llm_judge_per_user_daily_limit=0)

    out = await svc.judge(
        redis=fakeredis_client,
        user_id=7,
        definition_id=11,
        canonical="a feline",
        user_answer="cat",
        normalized="cat",
    )
    assert out == "incorrect"
    # counter incremented + TTL set on first use.
    assert await fakeredis_client.get(svc._user_counter_key(7)) == "1"
    assert await fakeredis_client.ttl(svc._user_counter_key(7)) > 0


async def test_over_budget_returns_incorrect(fakeredis_client, monkeypatch):
    _enable(monkeypatch)
    await fakeredis_client.set(svc._budget_key(), "5.0")

    out = await svc.judge(
        redis=fakeredis_client,
        user_id=2,
        definition_id=12,
        canonical="a feline",
        user_answer="cat",
        normalized="cat",
    )
    assert out == "incorrect"


async def test_success_caches_and_books_spend(fakeredis_client, monkeypatch):
    _enable(monkeypatch)
    _patch_client(monkeypatch, content="yes")

    out = await svc.judge(
        redis=fakeredis_client,
        user_id=3,
        definition_id=13,
        canonical="a feline",
        user_answer="a small cat",
        normalized="a small cat",
    )
    assert out == "correct"
    # verdict cached + budget incremented + budget TTL set.
    assert await fakeredis_client.get(svc._cache_key(13, "a small cat")) == "correct"
    assert float(await fakeredis_client.get(svc._budget_key())) > 0
    assert await fakeredis_client.ttl(svc._budget_key()) > 0


async def test_transport_error_degrades_to_incorrect(fakeredis_client, monkeypatch):
    _enable(monkeypatch)
    _patch_client(monkeypatch, raise_exc=httpx.ConnectError("boom"))

    out = await svc.judge(
        redis=fakeredis_client,
        user_id=4,
        definition_id=14,
        canonical="a feline",
        user_answer="cat",
        normalized="cat",
    )
    assert out == "incorrect"
    # no verdict cached on failure.
    assert await fakeredis_client.get(svc._cache_key(14, "cat")) is None


async def test_malformed_json_degrades_to_incorrect(fakeredis_client, monkeypatch):
    _enable(monkeypatch)

    class _BadResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"unexpected": "shape"}  # KeyError on ["choices"]

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _BadResp()

    monkeypatch.setattr(svc.httpx, "AsyncClient", _Client)

    out = await svc.judge(
        redis=fakeredis_client,
        user_id=5,
        definition_id=15,
        canonical="a feline",
        user_answer="cat",
        normalized="cat",
    )
    assert out == "incorrect"
