"""Provider isolation and mandatory HITL configuration contracts."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace

import pytest

from pycil.assistant.agent import graph, middleware
from pycil.assistant.agent import model as model_factory
from pycil.assistant.agent.tools import ALL_TOOLS


def test_assistant_provider_uses_only_dedicated_openai_compatible_settings(monkeypatch):
    """The provider credential is environmental; the model and budget are policy.

    Asserts the split this boundary exists for: the key and base URL come from the
    process environment, while the model id, its output ceiling and the turn's
    tool budget come from the committed catalog, so changing them is a config
    edit rather than a redeploy of environment values.
    """
    captured = {}

    class FakeModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    sentinel = object()
    default_model = SimpleNamespace(id="catalog-model", enabled=True, max_output_tokens=345)
    catalog = SimpleNamespace(
        assistant=SimpleNamespace(
            default_model="catalog-model",
            default_reasoning_effort="high",
            turn_timeout_seconds=12,
            max_tool_calls_per_turn=7,
        ),
        resolve_selection=lambda: (default_model, "high"),
    )
    monkeypatch.setattr(model_factory, "ChatOpenAI", FakeModel)
    monkeypatch.setattr(graph, "create_agent", lambda **kwargs: sentinel)
    monkeypatch.setattr(graph, "system_config", catalog)
    monkeypatch.setattr(model_factory, "system_config", catalog)
    provider_settings = SimpleNamespace(
        assistant_api_key="assistant-secret",
        assistant_base_url="https://provider.example/v1",
        assistant_context_window_tokens=8192,
    )
    monkeypatch.setattr(
        graph,
        "settings",
        provider_settings,
    )
    monkeypatch.setattr(model_factory, "settings", provider_settings)

    assert graph.build_graph(checkpointer=object()) is sentinel
    assert captured["api_key"] == "assistant-secret"
    assert captured["base_url"] == "https://provider.example/v1"
    assert captured["model"] == "catalog-model"
    assert captured["timeout"] == 12
    assert captured["max_completion_tokens"] == 345
    assert captured["extra_body"] == {"reasoning_effort": "high"}


def test_assistant_fails_closed_when_the_default_model_left_the_catalog(monkeypatch):
    """The graph refuses a model selection before constructing its provider client."""

    def reject_selection():
        raise ValueError("unknown_model")

    catalog = SimpleNamespace(
        assistant=SimpleNamespace(
            default_model="removed-model",
            default_reasoning_effort="none",
            turn_timeout_seconds=12,
            max_tool_calls_per_turn=7,
        ),
        resolve_selection=reject_selection,
    )
    monkeypatch.setattr(graph, "system_config", catalog)
    monkeypatch.setattr(
        graph,
        "settings",
        SimpleNamespace(
            assistant_api_key="assistant-secret",
            assistant_base_url="https://provider.example/v1",
        ),
    )
    with pytest.raises(ValueError, match="unknown_model"):
        graph.build_graph(checkpointer=object())


def test_assistant_provider_fails_closed_without_dedicated_credential(monkeypatch):
    monkeypatch.setattr(
        graph,
        "settings",
        SimpleNamespace(assistant_api_key="", assistant_base_url="https://provider.example/v1"),
    )
    with pytest.raises(RuntimeError, match="assistant_provider_not_configured"):
        graph.build_graph(checkpointer=object())


@pytest.mark.asyncio
async def test_selected_effort_overrides_the_default_model(monkeypatch):
    model = SimpleNamespace(id="default-model", enabled=True, max_output_tokens=120)
    monkeypatch.setattr(
        middleware,
        "system_config",
        SimpleNamespace(get_model=lambda model_id: model),
    )
    calls = []
    monkeypatch.setattr(
        middleware,
        "build_chat_model",
        lambda model_id, output, effort: calls.append((model_id, output, effort)) or "chosen",
    )
    request = SimpleNamespace(
        runtime=SimpleNamespace(
            context=SimpleNamespace(model_id="default-model", reasoning_effort="high")
        ),
        model=SimpleNamespace(model_name="default-model"),
        override=lambda **kwargs: SimpleNamespace(**kwargs),
    )

    await middleware.ModelSelectionMiddleware("none").awrap_model_call(
        request, lambda updated: _resolved(updated.model)
    )

    assert calls == [("default-model", 120, "high")]


async def _resolved(value):
    return value


@pytest.mark.asyncio
async def test_openai_compatible_client_invokes_configured_provider_protocol(monkeypatch):
    """Exercise the actual OpenAI-compatible wire protocol without a real secret."""
    received: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def _chunk(self, delta: dict, finish_reason: str | None = None) -> dict:
            return {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "compatible-test-model",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
            }

        def do_POST(self):  # noqa: N802 - stdlib HTTP hook name
            received["path"] = self.path
            received["authorization"] = self.headers.get("Authorization", "")
            self.rfile.read(int(self.headers["Content-Length"]))
            chunks = (
                self._chunk({"role": "assistant"}),
                self._chunk({"content": "pong"}),
                self._chunk({}, "stop"),
            )
            payload = (
                "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
            )
            payload = payload.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):  # noqa: A002
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setattr(
            model_factory,
            "system_config",
            SimpleNamespace(assistant=SimpleNamespace(turn_timeout_seconds=30)),
        )
        monkeypatch.setattr(
            model_factory,
            "settings",
            SimpleNamespace(
                assistant_api_key="test-key",
                assistant_base_url=f"http://127.0.0.1:{server.server_port}/v1",
            ),
        )
        model = model_factory.build_chat_model(
            model_id="compatible-test-model",
            max_output_tokens=100,
            reasoning_effort="none",
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
    expected = {"move_node", "publish_node", "delete_node", "remove_senses_from_deck"}
    assert set(graph.SENSITIVE_TOOLS) == expected
    assert all(
        item["allowed_decisions"] == ["approve", "reject"]
        for item in graph.SENSITIVE_TOOLS.values()
    )
    tools_by_name = {tool.name: tool for tool in ALL_TOOLS}
    assert expected <= set(tools_by_name)
    for name in expected:
        assert "Human approval is required" in (tools_by_name[name].description or "")


def test_the_agent_exposes_exactly_the_accepted_tool_set():
    """Set equality, not a count: a substitution would keep the size the same."""
    expected = {
        "list_nodes",
        "get_node",
        "create_folder",
        "create_deck",
        "rename_node",
        "move_node",
        "delete_node",
        "publish_node",
        "make_node_private",
        "search_word",
        "list_deck_items",
        "add_senses_to_deck",
        "remove_senses_from_deck",
        "folder_stats",
    }

    assert {tool.name for tool in ALL_TOOLS} == expected


def test_the_batch_and_unresolved_job_tools_are_the_accepted_ones():
    """Singular membership tools and the async generation request must be absent."""
    names = {tool.name for tool in ALL_TOOLS}

    assert "add_sense_to_deck" not in names
    assert "remove_sense_from_deck" not in names
    # An async request tool would leave the model with an unresolved job it
    # cannot report on; ordinary content flow triggers generation instead.
    assert "request_word_generation" not in names
