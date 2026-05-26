"""LLM call against OpenRouter via LangChain ChatOpenAI.

Adds an in-process fallback chain over `OPENROUTER_FALLBACK_CHAIN` plus
`generate_with_schema` legacy entrypoint. Retryable failures (5xx, 429,
timeout) hop to the next model; terminal failures (4xx) re-raise immediately.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from worker.config import get_settings
from worker.llm.exceptions import (
    OpenRouterAllModelsFailedError,
    OpenRouterTerminalError,
    classify_exception,
)

_log = logging.getLogger(__name__)
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"

T = TypeVar("T", bound=BaseModel)


@dataclass
class FallbackResult:
    """Outcome of a successful fallback-chain invocation."""

    output: Any
    model_used: str
    hops: int
    elapsed_seconds: float


@lru_cache(maxsize=8)
def _client(model: str | None = None) -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        base_url=_OPENROUTER_BASE,
        api_key=settings.openrouter_api_key,  # type: ignore[arg-type]
        model=model or settings.openrouter_model,
        temperature=0.3,
        timeout=settings.llm_timeout_seconds,
        max_retries=0,
    )


async def _invoke_one(model: str, prompt: str, schema: type[T]) -> T:
    structured = _client(model).with_structured_output(schema, method="json_mode")
    raw = await structured.ainvoke(prompt)  # type: ignore[arg-type]
    if isinstance(raw, schema):
        return raw
    return schema.model_validate(raw)


async def invoke_with_fallback(
    prompt: str,
    schema: type[T],
    *,
    models: list[str] | None = None,
    budget_seconds: float | None = None,
) -> FallbackResult:
    """Try each model in chain. Return first success; raise on full exhaustion.

    Retryable error → log + continue to next model.
    Terminal error → re-raise (no fallback; this is a real bug).
    Whole-chain wall budget enforced via asyncio.timeout.
    """
    settings = get_settings()
    chain = models if models is not None else settings.fallback_models
    if not chain:
        raise OpenRouterTerminalError("no_models_in_fallback_chain")
    budget = budget_seconds if budget_seconds is not None else settings.openrouter_fallback_budget_seconds

    started = time.monotonic()
    last_retryable: BaseException | None = None

    async def _run_chain() -> FallbackResult:
        nonlocal last_retryable
        for hop, model in enumerate(chain):
            try:
                output = await _invoke_one(model, prompt, schema)
            except OpenRouterTerminalError:
                raise
            except Exception as exc:  # noqa: BLE001
                cls = classify_exception(exc)
                if cls is OpenRouterTerminalError:
                    raise OpenRouterTerminalError(str(exc)[:300]) from exc
                last_retryable = exc
                _log.warning(
                    "llm_fallback_hop",
                    extra={
                        "model": model,
                        "hop": hop,
                        "err_type": type(exc).__name__,
                        "err": str(exc)[:300],
                    },
                )
                continue
            return FallbackResult(
                output=output,
                model_used=model,
                hops=hop,
                elapsed_seconds=time.monotonic() - started,
            )
        raise OpenRouterAllModelsFailedError(
            f"all_models_failed: {chain}"
        ) from last_retryable

    try:
        return await asyncio.wait_for(_run_chain(), timeout=budget)
    except asyncio.TimeoutError as exc:
        raise OpenRouterAllModelsFailedError(
            f"chain_budget_exceeded after {budget:.0f}s"
        ) from (last_retryable or exc)


async def generate_with_schema(prompt: str, schema: type[T]) -> T:
    """Legacy entrypoint kept for callers that don't need fallback metadata.

    Routes through the fallback chain so existing call sites benefit
    automatically without a refactor.
    """
    result = await invoke_with_fallback(prompt, schema)
    return result.output
