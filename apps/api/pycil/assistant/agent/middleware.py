"""Assistant model/tool middleware kept at the graph boundary."""

import logging

from langchain.agents.middleware import AgentMiddleware

from pycil.assistant.agent.model import build_chat_model
from pycil.assistant.turns.usage import CallUsage, call_usage, usage_units_for
from pycil.platform.product_config import system_config

logger = logging.getLogger(__name__)


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

    def __init__(self, default_effort: str) -> None:
        self.default_effort = default_effort

    async def awrap_model_call(self, request, handler):
        context = getattr(getattr(request, "runtime", None), "context", None)
        selected_id = getattr(context, "model_id", None)
        effort = getattr(context, "reasoning_effort", None)

        if selected_id and (
            selected_id != getattr(request.model, "model_name", None)
            or (effort or self.default_effort) != self.default_effort
        ):
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
    """Record one turn's settled usage and return its metered unit charge."""
    charge = usage_units_for(usage)
    logger.info(
        "assistant_turn_usage",
        extra={
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cached_input_tokens": usage.cached_input_tokens,
            "unpriced_cache_write_tokens": usage.unpriced_cache_write_tokens,
            "unmetered_calls": usage.unmetered_calls,
            "usage_units": charge,
            "units": charge,
            "milli_credits": charge,
        },
    )
    return charge
