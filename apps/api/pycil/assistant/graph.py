from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import langchain.agents as lc_agents
import langchain_core.messages as lc_messages
from langchain.agents.middleware import (
    AgentMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
    hook_config,
)
from langchain.agents.middleware.human_in_the_loop import InterruptOnConfig
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_openrouter import ChatOpenRouter
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.config import get_config
from openrouter import OpenRouter
from pydantic import ValidationError

from pycil.app.config import AppConfig
from pycil.app.http import Problem
from pycil.app.resources import RuntimeState
from pycil.app.settings import Deployment
from pycil.assistant.config import ModelPolicy
from pycil.assistant.tools import MUTATION_TOOLS, tools, validation_message
from pycil.infrastructure.observability import ObservedAsyncClient, get_logger

create_agent: Callable[..., Any] = cast(Any, lc_agents).create_agent
trim_messages: Callable[..., list[BaseMessage]] = cast(Any, lc_messages).trim_messages

logger = get_logger(__name__)


class Boundary(AgentMiddleware[Any, Any, Any]):
    config: AppConfig
    turn_context: str | None

    def __init__(self, config: AppConfig, turn_context: str | None = None) -> None:
        super().__init__()
        self.config = config
        self.turn_context = turn_context

    @hook_config(can_jump_to=["end"])
    async def aafter_model(self, state: Any, runtime: Any) -> dict[str, str] | None:
        if get_config().get("configurable", {}).get("reject_all"):
            return {"jump_to": "end"}
        return None

    async def awrap_model_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        req_messages = cast(list[BaseMessage], request.messages)
        human_indices = [
            i for i, message in enumerate(req_messages) if getattr(message, "type", None) == "human"
        ]
        position = max(human_indices)
        current = req_messages[position:]
        # Retain this turn's whole tool chain; trim only older conversation turns.
        trimmed: list[BaseMessage] = trim_messages(
            req_messages[:position],
            max_tokens=max(
                0, self.config.product.assistant.limits.max_context_messages - len(current)
            ),
            token_counter=len,
            strategy="last",
            start_on="human",
        )
        messages: list[BaseMessage] = trimmed + current
        # A failed/disconnected tool run can leave a call without its result in history.
        history: list[BaseMessage] = []
        pending: dict[str, dict[str, object]] = {}
        for message in [*messages, None]:
            if message is None or getattr(message, "type", None) != "tool":
                history.extend(
                    ToolMessage(
                        content="tool_result_unavailable",
                        tool_call_id=str(call["id"]),
                        name=str(call["name"]),
                        status="error",
                    )
                    for call in pending.values()
                )
                pending.clear()
            if message is None:
                break
            history.append(message)
            msg_type = getattr(message, "type", None)
            if msg_type == "ai":
                pending.update((call["id"], call) for call in getattr(message, "tool_calls", []))
            elif msg_type == "tool":
                pending.pop(getattr(message, "tool_call_id", ""), None)
        if self.turn_context is not None:
            human_pos = max(
                i for i, message in enumerate(history) if getattr(message, "type", None) == "human"
            )
            history.insert(human_pos + 1, HumanMessage(content=self.turn_context))
        logger.debug("assistant_llm_call_started")
        try:
            return await handler(request.override(messages=history))
        except Exception as exc:
            logger.error("assistant_llm_call_failed", error_type=type(exc).__name__)
            raise RuntimeError("assistant_provider_unavailable") from None

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        tool_name = str(request.tool_call["name"])
        tool_call_id = str(request.tool_call["id"])
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
        except Exception as error:
            logger.error(
                "assistant_tool_call_failed",
                tool_name=tool_name,
                error_type=type(error).__name__,
            )
            raise RuntimeError("assistant_tool_failed") from None


@asynccontextmanager
async def model(
    deployment: Deployment, policy: ModelPolicy, effort: str, timeout_seconds: float
) -> AsyncGenerator[ChatOpenRouter]:
    async with ObservedAsyncClient(follow_redirects=True) as http:
        selected = ChatOpenRouter(
            model=policy.id,
            api_key=deployment.llm_api_key,
            base_url=deployment.llm_base_url,
            timeout=int(timeout_seconds * 1000),
            app_url=None,
            app_title=None,
            max_tokens=policy.max_output_tokens,
            max_retries=0,
            # LangChain's zero leaves the SDK's default 5xx retry policy enabled.
            client=OpenRouter(
                api_key=deployment.llm_api_key.get_secret_value(),
                server_url=deployment.llm_base_url,
                timeout_ms=int(timeout_seconds * 1000),
                retry_config=None,
                async_client=http,
            ),
            reasoning={"effort": effort, "exclude": False},
            streaming=True,
            output_version="v1",
            stream_usage=True,
        )
        async with selected.client:
            yield selected


def graph(
    resources: RuntimeState,
    user: UUID,
    config: AppConfig,
    selected_model: ChatOpenRouter,
    *,
    auto_approve: bool = False,
    turn_context: str | None = None,
) -> Any:
    surface = tools(resources, user, config)
    protected_map: dict[str, bool | InterruptOnConfig] = {
        t.name: {"allowed_decisions": ["approve", "reject"]}
        for t in surface
        if t.name in MUTATION_TOOLS
    }
    interrupt_on: dict[str, bool | InterruptOnConfig] = {} if auto_approve else protected_map
    middleware_chain: Sequence[AgentMiddleware[Any, Any, Any]] = [
        Boundary(config, turn_context),
        HumanInTheLoopMiddleware(interrupt_on=interrupt_on),
        ToolCallLimitMiddleware(
            run_limit=config.product.assistant.limits.max_tool_calls, exit_behavior="error"
        ),
        ModelCallLimitMiddleware(
            run_limit=config.product.assistant.limits.max_tool_calls + 1, exit_behavior="error"
        ),
    ]
    return create_agent(
        selected_model,
        tools=surface,
        system_prompt=(Path(__file__).parent / "prompts/system_prompt.txt").read_text(),
        middleware=middleware_chain,
        checkpointer=AsyncPostgresSaver(resources.checkpoint_pool),
    )
