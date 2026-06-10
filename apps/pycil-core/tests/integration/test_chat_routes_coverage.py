"""Chat HTTP API coverage: sessions CRUD, message cap, SSE stream frames.

The `client` fixture overrides `get_current_user` -> test_user and
`get_session`. The SSE handler `_chat_stream` opens its OWN session via
`get_engine()` (redirected to the test engine by the `async_engine`
fixture), and calls `llm_streaming.stream_chat`, which we monkeypatch so
no OpenRouter network call happens.
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import text


async def _create_session(client) -> str:
    resp = await client.post("/chat/sessions", json={})
    assert resp.status_code == 200, resp.text
    return resp.json()["session_id"]


# ---------------------------------------------------------------------------
# Session lifecycle.
# ---------------------------------------------------------------------------

async def test_create_get_session(client) -> None:
    sid = await _create_session(client)
    resp = await client.get(f"/chat/sessions/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == sid
    assert body["total_input_tokens"] == 0
    assert body["status"] == "active"


async def test_get_session_404_unknown(client) -> None:
    resp = await client.get(f"/chat/sessions/{uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "session_not_found"


async def test_create_session_with_bad_deck_raises(client) -> None:
    """Unknown/inaccessible deck → chat_service raises LookupError.

    The route does not catch it, so under ASGITransport (raise_app_exceptions
    default) the exception propagates. The point: no session is silently
    created for a deck the user can't access.
    """
    with pytest.raises(LookupError):
        await client.post("/chat/sessions", json={"deck_id": str(uuid4())})


# ---------------------------------------------------------------------------
# Messages: list, append, input cap.
# ---------------------------------------------------------------------------

async def test_list_messages_empty(client) -> None:
    sid = await _create_session(client)
    resp = await client.get(f"/chat/sessions/{sid}/messages")
    assert resp.status_code == 200
    assert resp.json()["messages"] == []


async def test_send_message_then_listed(client) -> None:
    sid = await _create_session(client)
    resp = await client.post(
        f"/chat/sessions/{sid}/messages", json={"content": "hello tutor"}
    )
    assert resp.status_code == 200
    assert "message_id" in resp.json()

    listed = await client.get(f"/chat/sessions/{sid}/messages")
    msgs = listed.json()["messages"]
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "hello tutor"


async def test_send_message_unknown_session_404(client) -> None:
    resp = await client.post(
        f"/chat/sessions/{uuid4()}/messages", json={"content": "hi"}
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "session_not_found"


async def test_send_message_input_capped_429(client, session, test_user) -> None:
    """total_input_tokens >= 20_000 → 429 session_input_capped."""
    sid = await _create_session(client)
    await session.execute(
        text(
            "UPDATE chat_sessions SET total_input_tokens = 25000 WHERE id = :s"
        ),
        {"s": sid},
    )
    await session.commit()

    resp = await client.post(
        f"/chat/sessions/{sid}/messages", json={"content": "over the cap"}
    )
    assert resp.status_code == 429
    assert resp.json()["detail"] == "session_input_capped"


# ---------------------------------------------------------------------------
# Delete session.
# ---------------------------------------------------------------------------

async def test_delete_session(client) -> None:
    sid = await _create_session(client)
    resp = await client.delete(f"/chat/sessions/{sid}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1
    # Now gone.
    assert (await client.get(f"/chat/sessions/{sid}")).status_code == 404


async def test_delete_unknown_session_zero(client) -> None:
    resp = await client.delete(f"/chat/sessions/{uuid4()}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 0


# ---------------------------------------------------------------------------
# SSE stream: 404, token assembly + persistence, error frame.
# ---------------------------------------------------------------------------

def _parse_sse_events(body: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    cur_event = None
    for line in body.splitlines():
        if line.startswith("event: "):
            cur_event = line[len("event: "):]
        elif line.startswith("data: ") and cur_event is not None:
            events.append((cur_event, line[len("data: "):]))
    return events


async def test_stream_unknown_session_404(client) -> None:
    """Unknown session → 404 JSON (the guard runs before StreamingResponse).

    httpx returns the body fine here because the error path is a plain
    JSONResponse, not a StreamingResponse."""
    resp = await client.get(f"/chat/sessions/{uuid4()}/stream")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "session_not_found"


# The StreamingResponse body cannot be consumed over httpx ASGITransport when
# wrapped by Starlette BaseHTTPMiddleware (it re-emits http.request instead of
# http.disconnect mid-stream — a transport artifact, not a prod bug). So the
# token-assembly + persistence logic in `chat._chat_stream` is driven directly,
# exactly as the job-stream service generator is tested.

async def _drain_chat_stream(session_id, user_id) -> list[tuple[str, str]]:
    from pycil_core.api.routes import chat as chat_routes

    frames: list[tuple[str, str]] = []
    async for raw in chat_routes._chat_stream(session_id, user_id):
        frames.extend(_parse_sse_events(raw.decode()))
    return frames


async def test_stream_tokens_and_persist(client, session, test_user, monkeypatch) -> None:
    """Stub stream_chat → status+token+done frames; assistant msg persisted."""
    from uuid import UUID

    from pycil_core.services import llm_streaming

    async def fake_stream(messages, **kw):
        yield {"kind": "token", "token": "Hello"}
        yield {"kind": "token", "token": " world"}

    monkeypatch.setattr(llm_streaming, "stream_chat", fake_stream)

    sid = await _create_session(client)
    events = await _drain_chat_stream(UUID(sid), UUID(str(test_user["id"])))

    kinds = [e[0] for e in events]
    assert "status" in kinds
    assert kinds.count("token") == 2
    assert "done" in kinds
    tokens = [json.loads(d)["token"] for ev, d in events if ev == "token"]
    assert tokens == ["Hello", " world"]

    # Assistant message persisted with the assembled text.
    rows = (
        await session.execute(
            text(
                "SELECT role, content FROM chat_messages "
                "WHERE session_id = :s ORDER BY created_at"
            ),
            {"s": sid},
        )
    ).all()
    assert any(r.role == "assistant" and r.content == "Hello world" for r in rows)


async def test_stream_error_frame_aborts(client, session, test_user, monkeypatch) -> None:
    """An error frame ends the stream; no assistant message persisted."""
    from uuid import UUID

    from pycil_core.services import llm_streaming

    async def fake_stream(messages, **kw):
        yield {"kind": "error", "error": "openrouter_not_configured"}

    monkeypatch.setattr(llm_streaming, "stream_chat", fake_stream)

    sid = await _create_session(client)
    events = await _drain_chat_stream(UUID(sid), UUID(str(test_user["id"])))

    kinds = [e[0] for e in events]
    assert "error" in kinds
    assert "done" not in kinds

    rows = (
        await session.execute(
            text(
                "SELECT 1 FROM chat_messages "
                "WHERE session_id = :s AND role = 'assistant'"
            ),
            {"s": sid},
        )
    ).all()
    assert rows == []
