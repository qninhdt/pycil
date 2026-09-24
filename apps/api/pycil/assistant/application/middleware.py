"""Assistant model/tool middleware kept at the graph boundary."""

import json
import logging
from collections.abc import Mapping
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from pycil.assistant.domain.external_data import wrap_external_strings
from pycil.assistant.domain.usage import CallUsage, call_usage, milli_credits_for
from pycil.assistant.infra.model_factory import build_chat_model
from pycil.product_config import system_config

logger = logging.getLogger(__name__)


def cache_read_tokens(value: Any) -> int:
    """Extract provider cache-read usage without depending on one provider shape."""
    if isinstance(value, Mapping):
        total = 0
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in {
                "cache_read_input_tokens",
                "cache_read_tokens",
                "cached_tokens",
            }:
                try:
                    total += int(item or 0)
                except (TypeError, ValueError):
                    continue
            elif normalized in {"cache_read", "cached"}:
                try:
                    total += int(item or 0)
                except (TypeError, ValueError):
                    continue
            else:
                total += cache_read_tokens(item)
        return total
    if isinstance(value, list | tuple):
        return sum(cache_read_tokens(item) for item in value)
    return 0


class ExternalDataBoundaryMiddleware(AgentMiddleware):
    """Wrap tool output strings before they re-enter the model context."""

    async def awrap_tool_call(self, request, handler):
        result = await handler(request)
        if isinstance(result, ToolMessage):
            wrapped = wrap_external_strings(result.content)
            result = result.model_copy(
                update={
                    "content": json.dumps(
                        wrapped, sort_keys=True, separators=(",", ":"), default=str
                    )
                }
            )
        return result


class ModelSelectionMiddleware(AgentMiddleware):
    """Run each turn with the model and reasoning effort it selected.

    The graph is built once per process against the configured default, because
    ``create_agent`` binds one model. A turn that chose a different enabled model
    is switched here instead of rebuilding the graph per request, which would
    discard the compiled graph and its middleware on every turn.

    The selection has already been validated against the catalog by the router, so
    this resolves rather than re-validates; an unknown id falls back to the
    default instead of failing a turn that admission already accepted.
    """

    def __init__(self, default_model, default_effort: str) -> None:
        self.default_model = default_model
        self.default_effort = default_effort

    async def awrap_model_call(self, request, handler):
        context = getattr(getattr(request, "runtime", None), "context", None)
        selected_id = getattr(context, "model_id", None)
        effort = getattr(context, "reasoning_effort", None)

        if selected_id and selected_id != getattr(request.model, "model_name", None):
            model = system_config.get_model(selected_id)
            if model is not None and model.enabled:
                request = request.override(
                    model=build_chat_model(
                        model.id, model.max_output_tokens, effort or self.default_effort
                    )
                )
        return await handler(request)


class UsageMeteringMiddleware(AgentMiddleware):
    """Accumulate each model call's reported usage onto the run's context.

    This is the only place token usage is read, and it runs for every call in the
    agent loop, including the calls that follow a tool result. Nothing is charged
    here: the turn settles once, from the accumulated total, so a turn that makes
    three calls produces one ledger entry rather than three.
    """

    async def awrap_model_call(self, request, handler):
        response = await handler(request)
        context = getattr(getattr(request, "runtime", None), "context", None)
        usage = getattr(context, "usage", None)
        if usage is None:
            # No accumulator means the run cannot be metered. Recording the call
            # as unmetered keeps the omission visible instead of billing zero.
            logger.warning("assistant_usage_context_missing")
            return response

        # The tariff is per model, so the id is captured here rather than assumed
        # from configuration: a thread that switched models mid-turn must bill each
        # call at the rate it actually ran at.
        model_id = str(getattr(getattr(request, "model", None), "model_name", "") or "unknown")
        # Usage rides on the returned messages, not on the ModelResponse wrapper,
        # and one call may return more than one message.
        messages = getattr(response, "result", None) or [response]
        metered = False
        for message in messages:
            call = call_usage(message)
            if call.moved_tokens:
                usage.add(model_id, call)
                metered = True
        if not metered:
            # A call that reported nothing is recorded as unmetered so the turn is
            # flagged as under-metered rather than silently billed at zero.
            usage.add(model_id, CallUsage())
        logger.info(
            "assistant_model_usage",
            extra={
                "model": model_id,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cached_input_tokens": usage.cached_input_tokens,
                "unpriced_cache_write_tokens": usage.unpriced_cache_write_tokens,
                "unmetered_calls": usage.unmetered_calls,
            },
        )
        return response


def log_turn_usage(usage) -> int:
    """Record one turn's settled usage and return its milli-credit charge."""
    charge = milli_credits_for(usage)
    logger.info(
        "assistant_turn_usage",
        extra={
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cached_input_tokens": usage.cached_input_tokens,
            "unpriced_cache_write_tokens": usage.unpriced_cache_write_tokens,
            "unmetered_calls": usage.unmetered_calls,
            "milli_credits": charge,
        },
    )
    return charge
