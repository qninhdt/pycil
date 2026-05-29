"""LLM streaming via httpx against OpenRouter (OpenAI-compatible).

Used by chat-with-AI (phase 11). Worker keeps its own LangChain client
for batch jobs; chat is synchronous SSE on pycil-core, so it talks
directly to the HTTP API and yields tokens as they arrive.
"""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import httpx

from pycil_core.config import get_settings

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


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
    """
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
