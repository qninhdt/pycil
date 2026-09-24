"""Bounded LangChain graph construction using the OpenAI-compatible client."""

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, ToolCallLimitMiddleware

from pycil.assistant.application.attachments import HistoricalImageMiddleware
from pycil.assistant.application.middleware import (
    ExternalDataBoundaryMiddleware,
    ModelSelectionMiddleware,
    UsageMeteringMiddleware,
)
from pycil.assistant.application.tools import ALL_TOOLS
from pycil.assistant.application.trimming import TrimMessagesMiddleware
from pycil.assistant.domain.context import AssistantContext
from pycil.assistant.domain.prompts import SYSTEM_PROMPT
from pycil.assistant.infra.model_factory import build_chat_model
from pycil.config import settings
from pycil.product_config import system_config

SENSITIVE_TOOLS = {
    name: {"allowed_decisions": ["approve", "reject"]}
    for name in ("move_node", "publish_node", "delete_node", "remove_senses_from_deck")
}


def build_graph(checkpointer):
    """Build the agent only with a configured dedicated assistant credential."""
    if not settings.assistant_api_key or not settings.assistant_base_url:
        raise RuntimeError("assistant_provider_not_configured")
    assistant = system_config.assistant
    default_model, default_effort = system_config.resolve_selection()

    # The graph is built once per process and serves every learner, so the model
    # bound here is the configured default. A turn that selected another model is
    # switched per request by ModelSelectionMiddleware, which reads the validated
    # selection from the request context rather than rebuilding the graph.
    chat_model = build_chat_model(default_model.id, default_model.max_output_tokens, default_effort)

    return create_agent(
        model=chat_model,
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        context_schema=AssistantContext,
        checkpointer=checkpointer,
        middleware=[
            ModelSelectionMiddleware(default_model, default_effort),
            # Stripping precedes trimming so the token budget is computed against
            # the payload that is actually sent, not one still carrying history's
            # image bytes.
            HistoricalImageMiddleware(),
            TrimMessagesMiddleware(
                default_context_window_tokens=settings.assistant_context_window_tokens,
            ),
            UsageMeteringMiddleware(),
            ExternalDataBoundaryMiddleware(),
            ToolCallLimitMiddleware(
                run_limit=assistant.max_tool_calls_per_turn,
                exit_behavior="error",
            ),
            HumanInTheLoopMiddleware(interrupt_on=SENSITIVE_TOOLS),
        ],
    )
