"""A job the API queued is actually performed by the worker process.

This is the one fact the system level exists to establish and no lower level can: the
API publishes to a Redis Stream, a *different process* consumes it, calls the LLM
gateway over HTTP, writes a Lexi row, and the API can read a result back. Every piece
of that is real here — the broker, the consumer group, the provider call, the receipt.

The gateway is the only substitution, and it is a protocol substitution: the worker's
own OpenAI-compatible client parses its responses, so a wrong wire shape fails here
rather than passing.

The receipt's status vocabulary is the product's: `queued`, `running`, and the three
ways a job stops — `done`, `failed`, `expired`.
"""

import asyncio

import pytest

from tests.system.conftest import requires_stack

pytestmark = [pytest.mark.asyncio, requires_stack]

TERMINAL = {"done", "failed", "expired"}


async def _settled(caller, job_id: str, *, timeout: float = 90.0) -> dict:
    """Read the receipt until the worker has finished with it.

    Polling the *receipt* rather than resubmitting the work is the product's own rule:
    the generation is asynchronous and the job id is the handle to its progress. A
    journey that re-posted instead would start a second generation and pay for it.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    last: dict = {}
    while asyncio.get_running_loop().time() < deadline:
        last = await caller.ok("GET", f"/v1/jobs/{job_id}")
        if last["status"] in TERMINAL:
            return last
        await asyncio.sleep(0.25)
    raise AssertionError(f"job never settled: {last}")


async def test_a_word_generation_queued_by_the_api_is_performed_by_the_worker(actor):
    caller = actor.new()
    created = await caller.ok("POST", "/v1/word-generations", json={"query": "resilient"})

    receipt = await _settled(caller, created["taskId"])

    assert receipt["status"] == "done", receipt
    # The result names the Lexi rows the worker created, so the job really wrote.
    assert receipt["result"]["senseIds"], receipt


async def test_a_receipt_is_readable_only_by_the_learner_who_queued_it(actor):
    """A job id is not a capability: another learner guessing one gets a 404."""
    owner = actor.new()
    created = await owner.ok("POST", "/v1/word-generations", json={"query": "tenacious"})

    stranger = actor.new()
    response = await stranger.get(f"/v1/jobs/{created['taskId']}")

    assert response.status_code == 404
    assert response.json()["code"] == "job_not_found"


async def test_an_unknown_job_is_the_same_404_as_someone_elses(actor):
    """Indistinguishable on purpose: otherwise the route enumerates other learners."""
    caller = actor.new()

    unknown = await caller.get("/v1/jobs/does-not-exist")
    stranger = actor.new()
    created = await stranger.ok("POST", "/v1/word-generations", json={"query": "opaque"})
    other = await caller.get(f"/v1/jobs/{created['taskId']}")

    assert unknown.status_code == other.status_code == 404
    assert unknown.json()["code"] == other.json()["code"] == "job_not_found"


async def test_a_word_generation_outlives_the_worker_that_would_have_run_it(
    actor, system_stack, durable
):
    """Work published while no consumer exists is still performed, exactly once.

    This is the one journey that cannot exist below the system level: the failure is a
    *process* being gone, and what must survive is a message in a real Redis stream
    plus a receipt a client is polling. A fake cannot die.

    The consumer is stopped *before* the job is published, which is what makes the
    journey deterministic. Killing it after publishing would race the worker: the job
    often finishes first, and the test then passes without ever exercising recovery —
    the failure mode of a recovery test is being quietly vacuous.

    With no consumer, the message waits in the stream. The replacement worker then
    consumes it and the receipt reaches a terminal state, and the dictionary ends with
    exactly one entry for the word — so recovery neither lost the work nor ran it
    twice.

    Only the stack's own worker is stopped. A journey has no business signalling a
    process it did not start, which is why the harness owns the pid rather than
    matching a pattern.
    """
    caller = actor.new()

    system_stack.kill_worker()
    created = await caller.ok("POST", "/v1/word-generations", json={"query": "meticulous"})
    job_id = created["taskId"]

    # The work is durable while nothing is consuming it. The status is asserted
    # exactly: a ``done`` here would mean a consumer had already run the job, so the
    # kill had not removed the consumer and the recovery below would prove nothing.
    pending = await caller.ok("GET", f"/v1/jobs/{job_id}")
    assert pending["status"] == "queued", (
        f"the job was already consumed, so this journey is not exercising recovery: {pending}"
    )

    system_stack.start_worker()

    receipt = await _settled(caller, job_id, timeout=180.0)

    assert receipt["status"] == "done", receipt
    assert receipt["result"]["senseIds"], receipt

    # One generation, not two: a reclaimed message must not be re-executed into a
    # second word row for the same normalized query.
    assert (
        await durable.count("SELECT count(*) FROM lexi.words WHERE norm = $1", "meticulous") == 1
    ), "worker recovery produced a second dictionary entry for one word"
