"""Message-window trimming at the graph boundary.

LangChain's ``trim_messages`` already drops whole tool-call/tool-result groups
rather than splitting them, and can retain the system message across a cut, so
this module adds only the two decisions it cannot make for us: the token budget
and the token counter.

The counter is the provider's own approximation rather than a character-count
heuristic. A budget derived from a rough estimate would either trim earlier than
necessary or let an oversized window reach the provider, and the second failure
is the one a learner sees as a hard error.
"""

import json

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages

from pycil.platform.product_config import system_config

#: Reserve room for the model's reply. The window is a hard input limit, so the
#: budget must leave space for what comes back rather than filling it entirely.
OUTPUT_HEADROOM_TOKENS = 2_048


class TrimMessagesMiddleware(AgentMiddleware):
    """Trim each model request to the context window it will run against.

    Trimming happens per request and never writes back to graph state, so the
    durable conversation keeps every message: a later turn with a larger window
    still sees the full history.

    The budget comes from the model's own catalog entry rather than one process
    setting, because the catalog spans a 64k model and a 1M one. A single shared
    budget would either cut a large-window model's history short or let a
    small-window model's request exceed its limit.
    """

    def __init__(self, *, default_context_window_tokens: int) -> None:
        self.default_context_window_tokens = default_context_window_tokens

    def _window_for(self, request) -> int:
        model_id = getattr(getattr(request, "model", None), "model_name", None)
        if isinstance(model_id, str):
            spec = system_config.get_model(model_id)
            if spec is not None and spec.context_window > 0:
                return spec.context_window
        return self.default_context_window_tokens

    async def awrap_model_call(self, request, handler):
        model_id = getattr(getattr(request, "model", None), "model_name", None)
        spec = system_config.get_model(model_id) if isinstance(model_id, str) else None
        output_headroom = spec.max_output_tokens if spec else OUTPUT_HEADROOM_TOKENS
        system = getattr(request, "system_message", None)
        system_message = (
            system if isinstance(system, BaseMessage) else SystemMessage(content=str(system or ""))
        )
        system_tokens = count_tokens_approximately([system_message])
        tools = getattr(request, "tools", ()) or ()
        tool_schemas = []
        for tool in tools:
            if isinstance(tool, dict):
                tool_schemas.append(tool)
                continue
            schema = getattr(tool, "tool_call_schema", None)
            tool_schemas.append(
                {
                    "name": getattr(tool, "name", ""),
                    "description": getattr(tool, "description", ""),
                    "schema": schema.model_json_schema()
                    if hasattr(schema, "model_json_schema")
                    else {},
                }
            )
        tool_tokens = count_tokens_approximately(
            [SystemMessage(content=json.dumps(tool_schemas, default=str))]
        )
        budget = max(
            1, self._window_for(request) - output_headroom - system_tokens - tool_tokens - 256
        )
        messages: list[BaseMessage] = trim_messages(
            request.messages,
            max_tokens=budget,
            token_counter=count_tokens_approximately,
            strategy="last",
            include_system=True,
            allow_partial=False,
        )
        return await handler(request.override(messages=messages))
