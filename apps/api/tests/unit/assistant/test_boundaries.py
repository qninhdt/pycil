"""Focused safety and context-boundary tests for the assistant graph."""

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from pycil.assistant.agent.prompts import SYSTEM_PROMPT
from pycil.assistant.agent.tools import ALL_TOOLS
from pycil.assistant.agent.trimming import TrimMessagesMiddleware
from pycil.assistant.turns.usage import call_usage


def _usage_message(input_token_details):
    return SimpleNamespace(
        usage_metadata={"input_tokens": 100, "input_token_details": input_token_details}
    )


@pytest.mark.asyncio
async def test_trimming_keeps_the_system_prompt_and_whole_tool_pairs():
    """A trimmed window must stay sendable: paired tool messages and one system message."""
    middleware = TrimMessagesMiddleware(default_context_window_tokens=8_192)
    messages = [
        HumanMessage(content="old request " * 1_600),
        AIMessage(
            content="",
            tool_calls=[{"name": "get_node", "args": {"id": "1"}, "id": "call-1"}],
        ),
        ToolMessage(content="old tool result " * 1_600, tool_call_id="call-1"),
        HumanMessage(content="recent request"),
    ]

    captured = {}

    async def handler(request):
        captured["messages"] = request.messages
        return AIMessage(content="ok")

    await middleware.awrap_model_call(
        SimpleNamespace(
            messages=messages,
            system_message=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            override=lambda **kw: SimpleNamespace(**kw),
        ),
        handler,
    )

    trimmed = captured["messages"]
    assert trimmed[-1].content == "recent request"
    for index, message in enumerate(trimmed):
        if isinstance(message, AIMessage) and message.tool_calls:
            assert isinstance(trimmed[index + 1], ToolMessage)
            assert trimmed[index + 1].tool_call_id == message.tool_calls[0]["id"]


def test_prompt_scope_and_cache_usage_accept_provider_shapes():
    assert "dictionary search" in SYSTEM_PROMPT
    assert "word generation" not in SYSTEM_PROMPT
    # The three provider spellings of a cache read all mean one quantity.
    assert call_usage(_usage_message({"cache_read": 17})).cached_input_tokens == 17
    assert call_usage(_usage_message({"cached_tokens": 9})).cached_input_tokens == 9
    assert call_usage(_usage_message({"cache_read_input_tokens": 5})).cached_input_tokens == 5
