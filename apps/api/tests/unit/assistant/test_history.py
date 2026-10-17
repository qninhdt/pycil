from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import ValidationError

from pycil.app.config import load_config
from pycil.assistant.graph import Boundary
from pycil.assistant.schemas import NodeUpdate
from pycil.assistant.tools import validation_message


async def test_history_trim_keeps_current_tool_chain_and_fills_missing_results_without_mutation():
    config = load_config()
    config = config.model_copy(
        update={
            "assistant": config.assistant.model_copy(
                update={
                    "limits": config.assistant.limits.model_copy(update={"max_context_messages": 2})
                }
            )
        }
    )
    messages = [
        HumanMessage(content="old"),
        AIMessage(content="old reply"),
        HumanMessage(content="current"),
        AIMessage(
            content="",
            tool_calls=[
                {"name": "delete_nodes", "args": {}, "id": "missing"},
                {"name": "read_library", "args": {}, "id": "ready"},
            ],
        ),
        ToolMessage(content="read result", tool_call_id="ready"),
    ]
    request = SimpleNamespace(
        messages=messages, override=lambda **values: SimpleNamespace(**values)
    )
    captured = []

    async def handler(updated):
        captured.extend(updated.messages)
        return "result"

    boundary = Boundary(config.assistant, "<context>safe</context>")
    assert (await boundary.awrap_model_call(request, handler)) == "result"
    assert [message.content for message in captured if message.type == "human"] == [
        "current",
        "<context>safe</context>",
    ]
    assert [message.tool_call_id for message in captured if message.type == "tool"] == [
        "ready",
        "missing",
    ]
    assert captured[-1].content == "tool_result_unavailable" and captured[-1].status == "error"
    assert len(messages) == 5 and messages[-1].content == "read result"


def test_tool_validation_message_omits_submitted_input_and_exception_context():
    secret = "private-invalid-node-id"
    try:
        NodeUpdate(node_id=secret, name="name")
    except ValidationError as error:
        message = validation_message(error)
    assert "invalid_tool_arguments" in message
    assert secret not in message
    assert "input" not in message and "ctx" not in message
