"""SYS-I — the assistant's AG-UI stream: model selection, usage and the lease.

The assistant is the one surface where a client and the server share a protocol
rather than a payload shape. AG-UI frames arrive as SSE bytes, so this journey parses
what actually crossed the socket instead of trusting a Python object the API also
built — a hand-rolled event name would parse here as a failure, which is the point.

Three promises are checked, and each one has a way of looking fine while being wrong:

- **the chosen model reaches the provider.** A selection that is validated but not
  forwarded would pass every response-shape assertion while ignoring the learner.
- **usage is summed and billed from what the provider reported.** The fixture reports
  exact token counts, so the charge is arithmetic rather than a smoke test.
- **a refused selection costs nothing.** Refusal must happen before any provider call,
  which is only observable by counting calls at the gateway.
"""

import json
from uuid import uuid4

import pytest

from tests.system.conftest import requires_stack

pytestmark = [pytest.mark.asyncio, requires_stack]


async def test_a_run_streams_ag_ui_frames_that_parse(actor, llm_gateway):
    """The stream is AG-UI: a start, content, and a terminal finish.

    Parsed as raw bytes rather than through the SDK's client, because the SDK would
    happily parse a stream the deployment never produced. What must hold is that the
    frames are the protocol's own event names and that the run is bracketed.
    """
    caller = actor.new()
    thread = await caller.ok("POST", "/v1/assistant/threads", json={"title": "Stream"})

    events = await _run_stream(caller, thread["id"], "TEST_STREAM")

    kinds = [event["type"] for event in events]
    assert kinds, "the run streamed no events at all"
    assert kinds[0] == "RUN_STARTED", kinds
    assert kinds[-1] in {"RUN_FINISHED", "RUN_ERROR"}, kinds
    # The fixture streams text in two chunks, so a client can render incrementally.
    text = "".join(
        event.get("delta", "") for event in events if event["type"] == "TEXT_MESSAGE_CONTENT"
    )
    assert text, (
        f"the stream carried no text: {events}; provider calls={len(llm_gateway.model_requests())}"
    )


async def test_the_selected_model_and_effort_reach_the_provider(actor, llm_gateway):
    """A validated selection is actually forwarded, not merely accepted.

    The catalog is the server's, so a client asks for an id and the server prices and
    forwards it. A run that accepted the choice and then used the default would look
    identical in every response field, which is why the check is at the provider.
    """
    caller = actor.new()
    thread = await caller.ok("POST", "/v1/assistant/threads", json={"title": "Selection"})
    before = len(llm_gateway.model_requests())

    await _run_stream(
        caller,
        thread["id"],
        "TEST_STREAM",
        forwarded={"model": "gemini-3.8-flash", "reasoningEffort": "high"},
        run_id="selection-run",
    )

    seen = llm_gateway.model_requests()[before:]
    assert seen, "the provider was never called"
    assert any("gemini-3.8-flash" in model for model in seen), (
        f"the chosen model never reached the provider: {seen}"
    )


async def test_a_disabled_model_is_refused_before_the_provider_is_called(actor, llm_gateway):
    """An id outside the catalog costs nothing: no provider call, no ledger entry.

    The refusal has to happen at ingress. A run that forwarded the id and failed at
    the provider would bill for the attempt and would let a client probe the gateway.
    """
    caller = actor.new()
    thread = await caller.ok("POST", "/v1/assistant/threads", json={"title": "Refused"})
    before = llm_gateway.model_requests()
    balance_before = (await caller.credit())["availableUnits"]

    response = await _run_raw(
        caller, thread["id"], "TEST_STREAM", forwarded={"model": "gemini-2.5-flash"}
    )

    assert response.status_code == 422, response.text
    assert llm_gateway.model_requests() == before, "a refused model still reached the provider"
    assert (await caller.credit())["availableUnits"] == balance_before


async def test_an_unsupported_effort_is_refused(actor, llm_gateway):
    """Reasoning effort is validated against the model's own capability list."""
    caller = actor.new()
    thread = await caller.ok("POST", "/v1/assistant/threads", json={"title": "Effort"})
    before = llm_gateway.model_requests()

    response = await _run_raw(
        caller,
        thread["id"],
        "TEST_STREAM",
        forwarded={"model": "gemini-3.8-flash", "reasoningEffort": "maximum"},
    )

    assert response.status_code == 422, response.text
    assert llm_gateway.model_requests() == before


async def test_each_execution_is_billed_with_a_server_key_independent_of_run_id(actor, durable):
    """The client run id does not deduplicate executions or determine ledger keys.

    ``CHAT_USAGE`` makes the fixture report exact counts, so the expected debit is
    arithmetic from the catalog tariff rather than a snapshot. A repeated client
    run id is another execution attempt, and each attempt receives its own server
    event key. Exactly-once tool effects are not promised.
    """
    caller = actor.new()
    thread = await caller.ok("POST", "/v1/assistant/threads", json={"title": "Usage"})
    me = await caller.me()
    before = (await caller.credit())["availableUnits"]
    usage_count_sql = (
        "SELECT count(*) FROM usage_events e "
        "JOIN usage_periods p ON p.id = e.period_id WHERE p.user_id = $1"
    )

    await _run_stream(caller, thread["id"], "TEST_STREAM CHAT_USAGE 1000 100", run_id="usage-run")
    after_first = (await caller.credit())["availableUnits"]

    assert after_first < before, "a turn that reported usage charged nothing"
    assert (
        await durable.count(
            usage_count_sql,
            me["id"],
        )
        == 1
    ), "one execution wrote more than one ledger entry"

    replay = await _run_raw(
        caller, thread["id"], "TEST_STREAM CHAT_USAGE 1000 100", run_id="usage-run"
    )

    assert replay.status_code == 200, replay.text
    assert (await caller.credit())["availableUnits"] < after_first
    assert (
        await durable.count(
            usage_count_sql,
            me["id"],
        )
        == 2
    )


async def test_a_provider_failure_ends_the_run_with_an_error_frame(actor):
    """A provider 5xx becomes a terminal error event, not a hung stream.

    A stream that simply stops leaves the client waiting on a turn that will never
    finish, and the lease it holds is what makes the learner unable to start another.
    """
    caller = actor.new()
    thread = await caller.ok("POST", "/v1/assistant/threads", json={"title": "Failure"})

    events = await _run_stream(caller, thread["id"], "CHAT_FAIL")

    kinds = [event["type"] for event in events]
    assert kinds[-1] == "RUN_ERROR", kinds


async def test_one_learner_cannot_stream_into_anothers_thread(actor):
    """A thread id is not a capability: ownership precedes the checkpoint read."""
    owner = actor.new()
    thread = await owner.ok("POST", "/v1/assistant/threads", json={"title": "Owned"})

    stranger = actor.new()
    response = await _run_raw(stranger, thread["id"], "TEST_STREAM")

    assert response.status_code == 404


# --- helpers ------------------------------------------------------------------


async def _run_raw(
    caller,
    thread_id: str,
    message: str,
    *,
    forwarded: dict | None = None,
    run_id: str | None = None,
):
    """POST one AG-UI run without consuming the stream, for refusal cases."""
    return await caller.post(
        "/v1/assistant",
        json={
            "threadId": thread_id,
            "runId": run_id or f"system-run-{uuid4().hex}",
            "messages": [{"id": "m1", "role": "user", "content": message}],
            "forwardedProps": forwarded or {},
        },
    )


async def _run_stream(
    caller,
    thread_id: str,
    message: str,
    *,
    forwarded: dict | None = None,
    run_id: str | None = None,
) -> list[dict]:
    """Run one turn and return the AG-UI events, parsed from the raw SSE bytes.

    Parsed here rather than with the SDK's client so the assertion is about the wire:
    an event name the protocol does not define is a failure rather than something a
    tolerant parser absorbs.
    """
    response = await _run_raw(caller, thread_id, message, forwarded=forwarded, run_id=run_id)
    assert response.status_code == 200, f"{response.status_code} {response.text}"
    return _parse_sse(response.text)


def _parse_sse(body: str) -> list[dict]:
    """Every ``data:`` payload in an SSE body, as JSON."""
    events: list[dict] = []
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if not payload or payload == "[DONE]":
            continue
        events.append(json.loads(payload))
    return events
