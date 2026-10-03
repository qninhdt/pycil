from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)
from langchain_core.messages import trim_messages
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from pycil.assistant.tools import tools


class Boundary(AgentMiddleware):
    def __init__(self, config):
        self.config = config

    async def awrap_model_call(self, request, handler):
        messages = trim_messages(
            request.messages,
            max_tokens=self.config.assistant.max_context_messages,
            token_counter=len,
            strategy="last",
            start_on="human",
        )
        try:
            return await handler(request.override(messages=messages))
        except Exception:
            raise RuntimeError("assistant_provider_unavailable") from None

    async def awrap_tool_call(self, request, handler):
        try:
            return await handler(request)
        except Exception:
            raise RuntimeError("assistant_tool_failed") from None


def model(deployment, policy, effort, http):
    return ChatOpenAI(
        model=policy.id,
        api_key=deployment.inference_api_key.get_secret_value(),
        base_url=deployment.inference_base_url,
        max_tokens=policy.max_output_tokens,
        timeout=60,
        max_retries=0,
        reasoning_effort=None if effort == "none" else effort,
        stream_usage=True,
        http_async_client=http,
    )


def graph(resources, user, config, selected_model):
    surface = tools(resources, user, config)
    protected = {
        t.name: {"allowed_decisions": ["approve", "reject"]}
        for t in surface
        if t.name in {"create_collection", "update_collection", "delete_collection"}
    }
    return create_agent(
        selected_model,
        tools=surface,
        system_prompt=Path(__file__).with_name("prompt.md").read_text(),
        middleware=[
            Boundary(config),
            HumanInTheLoopMiddleware(interrupt_on=protected),
            ToolCallLimitMiddleware(
                run_limit=config.assistant.max_tool_calls, exit_behavior="error"
            ),
            ModelCallLimitMiddleware(
                run_limit=config.assistant.max_tool_calls + 1, exit_behavior="error"
            ),
        ],
        checkpointer=AsyncPostgresSaver(resources.checkpoint_pool),
    )
