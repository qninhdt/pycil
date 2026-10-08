from contextlib import asynccontextmanager
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
    hook_config,
)
from langchain_core.messages import trim_messages
from langchain_openrouter import ChatOpenRouter
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.config import get_config

from pycil.assistant.tools import tools


class Boundary(AgentMiddleware):
    def __init__(self, config):
        self.config = config

    @hook_config(can_jump_to=["end"])
    async def aafter_model(self, state, runtime):
        if get_config()["configurable"].get("reject_all"):
            return {"jump_to": "end"}

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


@asynccontextmanager
async def model(deployment, policy, effort, timeout_seconds):
    selected = ChatOpenRouter(
        model=policy.id,
        api_key=deployment.inference_api_key.get_secret_value(),
        base_url=deployment.inference_base_url,
        timeout=timeout_seconds * 1000,
        app_url=None,
        app_title=None,
        max_tokens=policy.max_output_tokens,
        max_retries=0,
        reasoning={"effort": effort, "exclude": False},
        streaming=True,
        output_version="v1",
        stream_usage=True,
    )
    async with selected.client:
        yield selected


def graph(resources, user, config, selected_model):
    surface = tools(resources, user, config)
    protected = {
        t.name: {"allowed_decisions": ["approve", "reject"]}
        for t in surface
        if t.name in {"create_node", "update_node", "delete_node"}
    }
    return create_agent(
        selected_model,
        tools=surface,
        system_prompt=Path(__file__).with_name("system_prompt.txt").read_text(),
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
