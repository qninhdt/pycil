"""LLM call against OpenRouter via LangChain ChatOpenAI.

Direct call from job code — no abstraction layer per user pref. Swap path is
editing this call site.
"""
from __future__ import annotations

import logging
from typing import TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from worker.config import get_settings
from worker.schemas.term_generation import TermGenerationOutput

_log = logging.getLogger(__name__)
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"

T = TypeVar("T", bound=BaseModel)


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


async def generate_term_payload(prompt: str) -> TermGenerationOutput:
    """Invoke the model with json_mode + Pydantic validation."""
    structured = _client().with_structured_output(
        TermGenerationOutput, method="json_mode"
    )
    raw = await structured.ainvoke(prompt)  # type: ignore[arg-type]
    if isinstance(raw, TermGenerationOutput):
        return raw
    return TermGenerationOutput.model_validate(raw)


async def generate_with_schema(prompt: str, schema: type[T]) -> T:
    """Generic schema-constrained call. Used by question generation."""
    structured = _client().with_structured_output(schema, method="json_mode")
    raw = await structured.ainvoke(prompt)  # type: ignore[arg-type]
    if isinstance(raw, schema):
        return raw
    return schema.model_validate(raw)
