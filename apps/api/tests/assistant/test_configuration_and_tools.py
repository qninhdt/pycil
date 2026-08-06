"""Provider-isolation and mandatory HITL configuration contracts."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace

import pytest

from pycil.assistant.application import graph
from pycil.assistant.application.tools import ALL_TOOLS


def test_assistant_provider_uses_only_dedicated_openai_compatible_settings(monkeypatch):
    captured = {}

    class FakeModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    sentinel = object()
    monkeypatch.setattr(graph, "ChatOpenAI", FakeModel)
    monkeypatch.setattr(graph, "create_agent", lambda **kwargs: sentinel)
    monkeypatch.setattr(
        graph,
        "settings",
        SimpleNamespace(
            assistant_api_key="assistant-secret",
            assistant_base_url="https://provider.example/v1",
            assistant_model="dedicated-model",
            assistant_timeout_seconds=12,
            assistant_max_output_tokens=345,
        ),
    )

    assert graph.build_graph(checkpointer=object()) is sentinel
    assert captured["api_key"] == "assistant-secret"
    assert captured["base_url"] == "https://provider.example/v1"


def test_assistant_provider_fails_closed_without_dedicated_credential(monkeypatch):
    monkeypatch.setattr(
        graph,
        "settings",
        SimpleNamespace(assistant_api_key="", assistant_base_url="https://provider.example/v1"),
    )
    with pytest.raises(RuntimeError, match="assistant_provider_not_configured"):
        graph.build_graph(checkpointer=object())


@pytest.mark.asyncio
async def test_openai_compatible_client_invokes_configured_provider_protocol():
    """Exercise the actual OpenAI-compatible wire protocol without a real secret."""
    received: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - stdlib HTTP hook name
            received["path"] = self.path
            received["authorization"] = self.headers.get("Authorization", "")
            self.rfile.read(int(self.headers["Content-Length"]))
            payload = json.dumps(
                {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "compatible-test-model",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "pong"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):  # noqa: A002
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        model = graph.ChatOpenAI(
            model="compatible-test-model",
            api_key="test-key",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            max_retries=0,
        )
        response = await model.ainvoke("ping")
    finally:
        server.shutdown()
        thread.join()
    assert response.content == "pong"
    assert received == {
        "path": "/v1/chat/completions",
        "authorization": "Bearer test-key",
    }


def test_every_sensitive_mutation_is_explicitly_interrupted_for_human_decision():
    expected = {"move_node", "publish_node", "delete_node", "remove_sense_from_deck"}
    assert set(graph.SENSITIVE_TOOLS) == expected
    assert all(
        item["allowed_decisions"] == ["approve", "reject"]
        for item in graph.SENSITIVE_TOOLS.values()
    )
    tools_by_name = {tool.name: tool for tool in ALL_TOOLS}
    assert expected <= set(tools_by_name)
    for name in expected:
        assert "Human approval is required" in (tools_by_name[name].description or "")
