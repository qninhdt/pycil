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
from langchain_core.messages import HumanMessage, ToolMessage, trim_messages
from langchain_openrouter import ChatOpenRouter
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.config import get_config
from pydantic import ValidationError

from pycil.assistant.tools import MUTATION_TOOLS, tools, validation_message
from pycil.http import Problem
from pycil.logging import get_logger

logger = get_logger(__name__)


class Boundary(AgentMiddleware):
    def __init__(self, config, turn_context=None):
        self.config = config
        self.turn_context = turn_context

    @hook_config(can_jump_to=["end"])
    async def aafter_model(self, state, runtime):
        if get_config()["configurable"].get("reject_all"):
            return {"jump_to": "end"}

    async def awrap_model_call(self, request, handler):
        position = max(i for i, message in enumerate(request.messages) if message.type == "human")
        current = request.messages[position:]
        # Retain this turn's whole tool chain; trim only older conversation turns.
        messages = (
            trim_messages(
                request.messages[:position],
                max_tokens=max(0, self.config.assistant.max_context_messages - len(current)),
                token_counter=len,
                strategy="last",
                start_on="human",
            )
            + current
        )
        # A failed/disconnected tool run can leave a call without its result in history.
        history, pending = [], {}
        for message in [*messages, None]:
            if message is None or message.type != "tool":
                history.extend(
                    ToolMessage(
                        content="tool_result_unavailable",
                        tool_call_id=call["id"],
                        name=call["name"],
                        status="error",
                    )
                    for call in pending.values()
                )
                pending.clear()
            if message is None:
                break
            history.append(message)
            if message.type == "ai":
                pending.update((call["id"], call) for call in message.tool_calls)
            elif message.type == "tool":
                pending.pop(message.tool_call_id, None)
        if self.turn_context is not None:
            position = max(i for i, message in enumerate(history) if message.type == "human")
            history.insert(position + 1, HumanMessage(content=self.turn_context))
        logger.debug("assistant_llm_call_started")
        try:
            return await handler(request.override(messages=history))
        except Exception as exc:
            logger.exception("assistant_llm_call_failed", error_type=type(exc).__name__)
            raise RuntimeError("assistant_provider_unavailable") from None

    async def awrap_tool_call(self, request, handler):
        tool_name = request.tool_call["name"]
        tool_call_id = request.tool_call["id"]
        logger.info(
            "assistant_tool_call_started",
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )
        try:
            return await handler(request)
        except Problem as exc:
            logger.warning(
                "assistant_tool_call_problem",
                tool_name=tool_name,
                status=exc.status,
                code=exc.code,
            )
            return ToolMessage(
                content=exc.code,
                tool_call_id=tool_call_id,
                name=tool_name,
                status="error",
            )
        except ValidationError as exc:
            logger.warning(
                "assistant_tool_validation_failed",
                tool_name=tool_name,
            )
            return ToolMessage(
                content=validation_message(exc),
                tool_call_id=tool_call_id,
                name=tool_name,
                status="error",
            )
        except Exception:
            logger.exception(
                "assistant_tool_call_failed",
                tool_name=tool_name,
            )
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


def graph(resources, user, config, selected_model, *, auto_approve=False, turn_context=None):
    surface = tools(resources, user, config)
    protected = {
        t.name: {"allowed_decisions": ["approve", "reject"]}
        for t in surface
        if t.name in MUTATION_TOOLS
    }
    return create_agent(
        selected_model,
        tools=surface,
        system_prompt=Path(__file__).with_name("system_prompt.txt").read_text(),
        middleware=[
            Boundary(config, turn_context),
            HumanInTheLoopMiddleware(interrupt_on={} if auto_approve else protected),
            ToolCallLimitMiddleware(
                run_limit=config.assistant.max_tool_calls, exit_behavior="error"
            ),
            ModelCallLimitMiddleware(
                run_limit=config.assistant.max_tool_calls + 1, exit_behavior="error"
            ),
        ],
        checkpointer=AsyncPostgresSaver(resources.checkpoint_pool),
    )
