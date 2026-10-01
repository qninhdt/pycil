"""A protocol-faithful LLM gateway for tests.

The application talks to an OpenAI-compatible endpoint, so this is a real HTTP
server speaking that protocol rather than a mock of Pycil's own provider client.
It serves the same wire shapes as the deployment: streamed `chat.completion.chunk`
frames, tool calls, structured `emit` responses, and — the part the golden provider
script omits — **reported usage metadata**, including cache-read detail.

Reported usage is what the credit ledger bills from. A stub that answers without it
would make every billing test measure a code path the deployment never takes, so
`usage` is on every response, and `CHAT_USAGE` lets a test state the exact numbers a
turn should be charged for.

Errors and malformed responses are first-class here because the interesting
behaviour is what the application does when a provider misbehaves: `FAIL` returns a
5xx, `SLOW` delays past a timeout, and `NO_USAGE` returns a well-formed completion
with the usage field absent.

Not a product script: nothing under `pycil/` imports this. It is test support.
"""

from __future__ import annotations

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

#: Per-million-token rates the tests assert against, matching `config/config.yaml`.
#: Kept here so a pricing test states the expected charge without reading the
#: catalog it is testing.
DEFAULT_PROMPT_TOKENS = 1_000
DEFAULT_COMPLETION_TOKENS = 100
DEFAULT_CACHED_TOKENS = 0


def _text(messages: list[dict[str, Any]]) -> str:
    return "\n".join(
        str(message.get("content", ""))
        for message in messages
        if isinstance(message, dict) and message.get("content") is not None
    )


def _target_word(messages: list[dict[str, Any]]) -> str:
    match = re.search(r"Generate the dictionary entry for:\s*([^\n]+)", _text(messages))
    return (match.group(1).strip() if match else "resilient")[:128]


def _resolve(spec: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    """Follow a local ``$ref`` to its definition.

    The structured-output schemas are not flat: a unit's senses are a ``$ref`` into
    ``$defs``. Skipping this step silently degrades every nested object to a string,
    which then fails deep inside the application with an error that says nothing about
    the fixture. A ``$ref`` cycle would loop forever, so a definition already on the
    current path is left unresolved rather than expanded again.
    """
    seen: set[str] = set()
    while isinstance(spec, dict) and isinstance(spec.get("$ref"), str):
        reference = spec["$ref"]
        if reference in seen or not reference.startswith("#/"):
            return spec
        seen.add(reference)
        node: Any = root
        for part in reference[2:].split("/"):
            if not isinstance(node, dict):
                return spec
            node = node.get(part)
        if not isinstance(node, dict):
            return spec
        # A sibling of `$ref` (a description, say) is preserved by the caller's own
        # keys; only the referenced body matters for filling values.
        spec = node
    return spec


#: Fields whose accepted values are narrower than their JSON schema says.
#:
#: A real model answers these from world knowledge; a filler that echoes the target
#: word does not. ``cefr_level`` is the case that forced this table: the schema
#: declares it an unconstrained string, the column is ``varchar(8)``, and the only
#: valid contents are the six CEFR bands — so the generic value fails at INSERT, far
#: from the fixture, with an error about a column nobody was thinking about.
#:
#: ``tag`` is here for a sharper reason: a topic is a **shared vocabulary**, and
#: echoing the headword into it makes every word its own only topic. Question
#: preparation draws multiple-choice distractors from words sharing a topic, so a
#: per-word topic leaves that ladder with nothing but the target — which the dedup
#: then correctly rejects as the answer. Preparation silently produced zero items and
#: the supply job failed with nothing in the logs pointing at the topic.
#:
#: Keyed by field name rather than by schema path because these are dictionary
#: concepts, not positions: a sense's CEFR level means the same thing wherever it is
#: asked for. ``tag`` and ``title`` occur on exactly one schema in Lexi —
#: ``GeneratedTopic`` — so naming them here cannot capture an unrelated field.
_FIELD_VALUES: dict[str, Any] = {
    "cefr_level": "B1",
    "ipa_uk": "/rɪˈzɪl.i.ənt/",
    "ipa_us": "/rɪˈzɪl.i.ənt/",
    "guideword": "able to recover",
    "domain": "general",
    "register": "neutral",
    "connotation": "neutral",
    "tier": "core",
    "tag": "learning",
    "title": "Learning",
}


def _value(name: str, spec: dict[str, Any], root: dict[str, Any], target: str) -> Any:
    """Fill a JSON-schema-shaped structure with deterministic values.

    Constraints are honoured rather than ignored. A schema that says ``enum`` or
    ``anyOf`` describes a closed set, and answering outside it produces a response the
    application's own pydantic model rejects — the job fails inside Lexi with a
    validation error that says nothing about the fixture, which is exactly the kind of
    failure a test double must not create.
    """
    spec = _resolve(spec, root)

    # A closed set: answer with a member. `anyOf`/`oneOf` pick the first branch that
    # is not just `null`, so a nullable field gets a real value rather than None.
    if isinstance(spec.get("enum"), list) and spec["enum"]:
        return spec["enum"][0]
    for keyword in ("anyOf", "oneOf"):
        branches = [branch for branch in spec.get(keyword) or [] if branch.get("type") != "null"]
        if branches:
            return _value(name, branches[0], root, target)
    if spec.get("const") is not None:
        return spec["const"]

    kind = spec.get("type")
    if kind is None and isinstance(spec.get("properties"), dict):
        kind = "object"
    if kind == "object":
        properties = spec.get("properties") or {}
        # A schema with no declared properties accepts any object; an empty one is
        # what the caller expects, and inventing keys would fail `additionalProperties`.
        return {key: _value(key, child, root, target) for key, child in properties.items()}
    if kind == "array":
        item = _resolve(spec.get("items") or {"type": "string"}, root)
        count = 1 if item.get("type") == "object" else 2
        return [_value(name, item, root, target) for _ in range(count)]
    if kind == "integer":
        return 1
    if kind == "number":
        return 1.0
    if kind == "boolean":
        return True

    if name in _FIELD_VALUES:
        return _FIELD_VALUES[name]

    value = {
        "word": target,
        "definition": f"definition of {target}",
        # An example must contain the target for a cloze to have something to blank,
        # and the markup is how the target is marked. A bare word here leaves the
        # cloze builder to its untagged fallback, which cannot blank an inflected
        # surface — so the fixture would under-supply exactly the types that need it.
        "examples": f'The <t inf="base">{target}</t> example helps learners.',
    }.get(name, target)
    limit = spec.get("maxLength")
    return value[:limit] if isinstance(limit, int) and limit > 0 else value


def _structured_args(body: dict[str, Any]) -> dict[str, Any]:
    tools = body.get("tools") or []
    function = (tools[0] if tools else {}).get("function", {})
    schema = function.get("parameters") or {}
    result = _value("root", schema, schema, _target_word(body.get("messages", [])))
    if isinstance(result, dict) and "correct" in result:
        correct = "WRONG" not in _text(body.get("messages", [])).upper()
        result["correct"] = correct
        result["score"] = 1.0 if correct else 0.0
        result["feedback"] = "Good use of the word." if correct else "Try the word again."
    return result


def _assistant_call(body: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    tools = body.get("tools") or []
    names = {tool.get("function", {}).get("name") for tool in tools if isinstance(tool, dict)}
    messages = body.get("messages") or []
    last_user = max(
        (
            index
            for index, message in enumerate(messages)
            if isinstance(message, dict) and message.get("role") == "user"
        ),
        default=-1,
    )
    prompt = str(messages[last_user].get("content", "")) if last_user >= 0 else ""
    has_tool_result = any(
        isinstance(message, dict) and (message.get("role") == "tool" or message.get("tool_calls"))
        for message in messages[last_user + 1 :]
    )
    if has_tool_result:
        return None
    if "list_nodes" in names and "TEST_LIST_NODES" in prompt:
        return "list_nodes", {"parent_id": None, "limit": 10}
    if "create_deck" in names and "TEST_CREATE_DECK" in prompt:
        match = re.search(r"TEST_CREATE_DECK ([^\n]+)", prompt)
        if match:
            return "create_deck", {"name": match.group(1).strip(), "parent_id": None}
    if "add_senses_to_deck" in names and "TEST_ADD_SENSES" in prompt:
        match = re.search(r"TEST_ADD_SENSES ([0-9a-fA-F-]{36}) ([0-9,]+)", prompt)
        if match:
            return "add_senses_to_deck", {
                "deck_id": match.group(1),
                "sense_ids": [int(part) for part in match.group(2).split(",")],
            }
    if "delete_node" in names and "TEST_APPROVAL" in prompt:
        match = re.search(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}",
            prompt,
        )
        if match:
            return "delete_node", {"node_id": match.group(0)}
    return None


def _usage(body: dict[str, Any]) -> dict[str, Any] | None:
    """The usage block a provider reports, or None when the test suppresses it."""
    if "NO_USAGE" in _text(body.get("messages") or []):
        return None
    match = re.search(r"CHAT_USAGE (\d+) (\d+)(?: (\d+))?", _text(body.get("messages") or []))
    prompt_tokens, completion_tokens = DEFAULT_PROMPT_TOKENS, DEFAULT_COMPLETION_TOKENS
    cached_tokens = DEFAULT_CACHED_TOKENS
    if match:
        prompt_tokens = int(match.group(1))
        completion_tokens = int(match.group(2))
        cached_tokens = int(match.group(3) or 0)
    usage: dict[str, Any] = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    if cached_tokens:
        usage["prompt_tokens_details"] = {"cached_tokens": cached_tokens}
    return usage


def _payload(body: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None, str]:
    tools = body.get("tools") or []
    if tools and tools[0].get("function", {}).get("name") == "emit":
        return "emit", _structured_args(body), ""
    call = _assistant_call(body)
    if call is not None:
        return call[0], call[1], ""
    if "TEST_STREAM" in _text(body.get("messages") or []):
        return None, None, "The deterministic provider streamed this response in two parts."
    return None, None, "The deterministic provider completed this turn."


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path.rstrip("/").endswith("/health"):
            self._json(200, {"status": "ok"})
            return
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": {"message": "invalid json"}})
            return

        prompt = _text(body.get("messages") or [])
        model = body.get("model")
        if isinstance(model, str):
            self.server.models.append(model)  # type: ignore[attr-defined]
        self.server.bodies.append(raw.decode(errors="replace"))  # type: ignore[attr-defined]
        if "CHAT_FAIL" in prompt:
            self._json(500, {"error": {"message": "provider unavailable"}})
            return
        if "CHAT_SLOW" in prompt:
            time.sleep(float(self.server.slow_seconds))  # type: ignore[attr-defined]

        name, args, text = _payload(body)
        usage = _usage(body)
        stream = bool(body.get("stream"))
        if stream:
            self._stream(name, args, text, usage)
            return
        self._completion(name, args, text, usage)

    def _stream(
        self,
        name: str | None,
        args: dict[str, Any] | None,
        text: str,
        usage: dict[str, Any] | None,
    ) -> None:
        chunks: list[dict[str, Any]] = [
            {"role": "assistant", "content": None} if name else {"role": "assistant"}
        ]
        if name:
            chunks.append(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_test_1",
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args or {})},
                        }
                    ]
                }
            )
        else:
            # Two content chunks so a test can assert the stream is incremental
            # rather than delivered as one frame.
            half = max(1, len(text) // 2)
            chunks.append({"content": text[:half]})
            chunks.append({"content": text[half:]})

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for delta in chunks:
            frame = {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "test-model",
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
            self.wfile.write(f"data: {json.dumps(frame)}\n\n".encode())
        final: dict[str, Any] = {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "tool_calls" if name else "stop",
                }
            ],
        }
        if usage is not None:
            final["usage"] = usage
        self.wfile.write(f"data: {json.dumps(final)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")

    def _completion(
        self,
        name: str | None,
        args: dict[str, Any] | None,
        text: str,
        usage: dict[str, Any] | None,
    ) -> None:
        message: dict[str, Any] = {"role": "assistant", "content": None if name else text}
        if name:
            message["tool_calls"] = [
                {
                    "id": "call_test_1",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args or {})},
                }
            ]
        payload: dict[str, Any] = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": "tool_calls" if name else "stop",
                }
            ],
        }
        if usage is not None:
            payload["usage"] = usage
        self._json(200, payload)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: Any) -> None:
        """Silence the stub's access log; the test's own output is the signal."""


class LlmGateway:
    """A running gateway on an ephemeral port.

    It records each request body as well as the model it asked for, because several
    contracts are only observable at the provider: whether a chosen model was actually
    forwarded, whether an image arrived as multimodal content, and whether a later turn
    re-sent image bytes the provider already processed. In every case the application's
    own responses look identical either way.
    """

    def __init__(self, *, slow_seconds: float = 30.0) -> None:
        self._models: list[str] = []
        self._bodies: list[str] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.slow_seconds = slow_seconds  # type: ignore[attr-defined]
        self._server.models = self._models  # type: ignore[attr-defined]
        self._server.bodies = self._bodies  # type: ignore[attr-defined]
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/v1"

    def model_requests(self) -> list[str]:
        """Every model id requested so far, oldest first.

        Returned as a copy so a journey can diff two readings without the list
        changing underneath it.
        """
        return list(self._models)

    def requests(self) -> list[str]:
        """Every request body received so far, oldest first, as raw JSON text.

        Raw rather than parsed: the assertions built on it are about what actually
        crossed the wire — an image's base64 payload, a model id, a marker — and
        parsing first would let the fixture's own shape decide what counts.
        """
        return list(self._bodies)

    def start(self) -> LlmGateway:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=5)
        self._server.server_close()


def start_gateway(*, slow_seconds: float = 30.0) -> LlmGateway:
    return LlmGateway(slow_seconds=slow_seconds).start()
