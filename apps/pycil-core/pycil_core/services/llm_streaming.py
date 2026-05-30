"""LLM streaming via httpx against OpenRouter (OpenAI-compatible).

Used by chat-with-AI (phase 11). Worker keeps its own LangChain client
for batch jobs; chat is synchronous SSE on pycil-core, so it talks
directly to the HTTP API and yields tokens as they arrive.

When LLM_STUB_MODE=true, yields a canned chat response instead of
calling OpenRouter (e2e test cost avoidance).
"""
from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator

import httpx

from pycil_core.config import get_settings

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_CANNED_CHAT = (
    "That's a great question! In English, 'ephemeral' means something "
    "that lasts for a very short time or is fleeting and transient. "
    "It comes from the Greek word 'ephemeros', meaning 'lasting only one day.' "
    "You might describe a sunset, a trend, or a moment of joy as ephemeral."
)


def _is_stub_mode() -> bool:
    return os.environ.get("LLM_STUB_MODE", "").lower() in ("1", "true", "yes")


async def _yield_canned_chat() -> AsyncGenerator[dict, None]:
    """Yield the canned response word by word to simulate streaming."""
    words = _CANNED_CHAT.split(" ")
    for i, word in enumerate(words):
        token = word if i == 0 else f" {word}"
        yield {"kind": "token", "token": token}
    yield {"kind": "usage", "usage": {"completion_tokens": len(_CANNED_CHAT.split())}}  # type: ignore[typeddict-item]


async def stream_chat(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 8000,
    temperature: float = 0.5,
) -> AsyncGenerator[dict, None]:
    """Yield {kind: 'token'|'usage'|'error', ...} dicts.

    Caller is responsible for persisting the assembled assistant message.
    Token stream stops on `[DONE]` sentinel; usage frame (if returned by
    OpenRouter) follows it.

    When LLM_STUB_MODE=true, yields a canned chat response without
    calling OpenRouter (no settings load needed).
    """
    if _is_stub_mode():
        async for token in _yield_canned_chat():
            yield token
        return

    settings = get_settings()
    api_key = getattr(settings, "openrouter_api_key", None)
    model = getattr(settings, "openrouter_chat_model", None) or getattr(
        settings, "openrouter_model", None
    )
    if not api_key or not model:
        yield {"kind": "error", "error": "openrouter_not_configured"}
        return

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST", _OPENROUTER_URL, json=payload, headers=headers
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    yield {
                        "kind": "error",
                        "error": f"openrouter_{response.status_code}",
                        "detail": body.decode("utf-8", "replace")[:500],
                    }
                    return

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        return
                    try:
                        frame = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = frame.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield {"kind": "token", "token": content}
                    if usage := frame.get("usage"):
                        yield {"kind": "usage", "usage": usage}
    except httpx.HTTPError as exc:
        yield {"kind": "error", "error": "network_error", "detail": str(exc)[:200]}
