"""Bounded LangChain graph construction using the OpenAI-compatible client."""

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, ToolCallLimitMiddleware
from langchain_openai import ChatOpenAI

from pycil.assistant.context import AssistantContext
from pycil.assistant.prompts import SYSTEM_PROMPT
from pycil.assistant.tools import ALL_TOOLS
from pycil.config import settings

SENSITIVE_TOOLS = {
    "move_node": {"allowed_decisions": ["approve", "reject"]},
    "publish_node": {"allowed_decisions": ["approve", "reject"]},
    "delete_node": {"allowed_decisions": ["approve", "reject"]},
    "remove_sense_from_deck": {"allowed_decisions": ["approve", "reject"]},
}


def build_graph(checkpointer):
    """Build the agent only with a configured dedicated assistant credential."""
    if not settings.assistant_api_key or not settings.assistant_base_url:
        raise RuntimeError("assistant_provider_not_configured")
    extra_body = {}
    if getattr(settings, "assistant_reasoning_effort", None):
        extra_body["reasoning_effort"] = settings.assistant_reasoning_effort

    model = ChatOpenAI(
        model=settings.assistant_model,
        api_key=settings.assistant_api_key,
        base_url=settings.assistant_base_url,
        timeout=settings.assistant_timeout_seconds,
        max_completion_tokens=settings.assistant_max_output_tokens,
        streaming=True,
        max_retries=0,
        extra_body=extra_body if extra_body else None,
    )
    return create_agent(
        model=model,
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        context_schema=AssistantContext,
        checkpointer=checkpointer,
        middleware=[
            ToolCallLimitMiddleware(
                run_limit=getattr(settings, "assistant_max_tool_calls", 12),
                exit_behavior="error",
            ),
            HumanInTheLoopMiddleware(interrupt_on=SENSITIVE_TOOLS),
        ],
    )
