"""The test LLM gateway speaks the protocol the application bills from.

The gateway is test support, but it is not a mock: the application's own
OpenAI-compatible client parses these responses, so a wrong shape here would make a
passing test prove nothing. Each case drives the real client against the real
server.
"""

import json
import time

import openai
import pytest
from langchain_openai import ChatOpenAI

from tests.support.llm_gateway import start_gateway

pytestmark = pytest.mark.asyncio


@pytest.fixture
def gateway():
    server = start_gateway(slow_seconds=5.0)
    try:
        yield server
    finally:
        server.stop()


def _model(gateway, *, timeout: float = 10.0) -> ChatOpenAI:
    return ChatOpenAI(
        model="test-model",
        api_key="test-key",
        base_url=gateway.base_url,
        timeout=timeout,
        max_retries=0,
    )


async def test_a_plain_completion_returns_text_and_reported_usage(gateway):
    response = await _model(gateway).ainvoke("hello")

    assert "deterministic provider completed this turn" in str(response.content)
    assert response.usage_metadata is not None
    assert response.usage_metadata["input_tokens"] > 0
    assert response.usage_metadata["output_tokens"] > 0


async def test_explicit_usage_numbers_are_reported_verbatim(gateway):
    """A billing test states the numbers it expects to be charged for."""
    response = await _model(gateway).ainvoke("CHAT_USAGE 500 100")

    assert response.usage_metadata["input_tokens"] == 500
    assert response.usage_metadata["output_tokens"] == 100


async def test_cache_read_tokens_are_reported_separately_from_input(gateway):
    """Cache detail is what separates a cached read's rate from an uncached one."""
    response = await _model(gateway).ainvoke("CHAT_USAGE 500 100 300")

    assert response.usage_metadata["input_tokens"] == 500
    details = response.usage_metadata.get("input_token_details") or {}
    assert details.get("cache_read") == 300


async def test_a_streamed_response_arrives_in_several_content_chunks(gateway):
    chunks = [
        chunk
        async for chunk in _model(gateway).astream("TEST_STREAM")
        if chunk.content
    ]

    assert len(chunks) >= 2


async def test_a_tool_call_is_returned_as_a_tool_call(gateway):
    model = _model(gateway).bind_tools(
        [
            {
                "type": "function",
                "function": {
                    "name": "list_nodes",
                    "description": "list nodes",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "parent_id": {"type": "string"},
                            "limit": {"type": "integer"},
                        },
                    },
                },
            }
        ]
    )

    response = await model.ainvoke("TEST_LIST_NODES")

    assert response.tool_calls
    assert response.tool_calls[0]["name"] == "list_nodes"
    assert response.tool_calls[0]["args"]["limit"] == 10


async def test_a_provider_error_surfaces_as_an_error(gateway):
    with pytest.raises(Exception, match=r"provider unavailable|500"):
        await _model(gateway).ainvoke("CHAT_FAIL")


async def test_a_suppressed_usage_block_is_absent_rather_than_zero(gateway):
    """A missing usage field must be distinguishable from a reported zero."""
    response = await _model(gateway).ainvoke("NO_USAGE")

    assert "deterministic provider completed this turn" in str(response.content)
    assert not response.usage_metadata or not response.usage_metadata.get("input_tokens")


async def test_a_slow_provider_exceeds_a_short_timeout(gateway):
    """A stalled provider must surface as a failure, not hang the caller."""
    started = time.monotonic()
    with pytest.raises(openai.APITimeoutError):
        await _model(gateway, timeout=0.5).ainvoke("CHAT_SLOW")
    assert time.monotonic() - started < 5


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
def test_the_gateway_is_not_imported_by_production_code():
    """Test support must not leak into the application."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    for package in (root / "pycil", root.parent / "worker" / "pycil_worker"):
        for source in package.rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            assert "tests.support" not in text, source
            assert "llm_gateway" not in text, source


@pytest.mark.filterwarnings("ignore::pytest.PytestWarning")
def test_the_health_endpoint_answers(gateway):
    import urllib.request

    with urllib.request.urlopen(gateway.base_url.replace("/v1", "/health")) as response:
        assert json.loads(response.read())["status"] == "ok"
