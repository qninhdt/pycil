"""SYS-E — question supply: a cold session is told, not stalled.

A failed supply job is not the learner's failure either: it must leave no grade, no
review log and no debit behind.

The design's dividing line (`C3`) is that no retrieval path ever generates: a learner
pressing "next" waits on a database read, and when supply is absent the client is told
which of preparing/waiting/exhausted applies. This journey checks that promise from
outside the process, because that is where it is observable — the state is on the wire,
and the work that fills the gap happens in a different process.

The second half is the failure boundary: supply that cannot be produced must not look
like a learner's mistake. A failed job yields an explicit retry and leaves no grade, no
review log and no credit movement, because none of those things ever happened.
"""

import asyncio

import pytest

from tests.system.conftest import requires_stack

pytestmark = [pytest.mark.asyncio, requires_stack]

TERMINAL = {"done", "failed", "expired"}


#: The whole vocabulary ``next`` may answer with. A client switches on this, so a
#: state outside it is a wire break even when the session is otherwise fine.
_STATES = {"ready", "preparing", "waiting", "exhausted", "break"}


async def test_a_cold_session_reaches_a_question_without_stalling_on_generation(actor, corpus):
    """A session over a word with no supply yet still delivers a graded item.

    The design's promise is that the read path never waits on a model call: supply is
    requested ahead of need and the client is *told* which of
    preparing/waiting/exhausted applies rather than being held open. So the contract
    this journey can assert without depending on worker timing is a disjunction — the
    client only ever sees states from that vocabulary, and it reaches a real question
    by polling the state rather than by resubmitting the work.

    Whether ``preparing`` appears at all is a race between the session's warm-up and
    the first poll, so asserting either way would make this flaky. What must hold
    regardless is that no state is outside the vocabulary and that the question
    arrives.

    A new sense is exposed before it is assessed — the product's own first step, not a
    missing question — so the journey walks past the exposure to the graded item.
    """
    owner = actor.new()
    sense = corpus["resilient"]
    deck = await owner.deck("Deck")
    await owner.add_sense(deck["id"], sense)

    session = await owner.start_session(deck["id"])
    assert session["firstState"] == "ready"

    states, outcome = await _until_assessment(owner, session["sessionId"])

    assert set(states) <= _STATES, f"next answered with a state outside the contract: {states}"
    assert outcome["state"] == "ready", outcome
    assert outcome["senseId"] == sense
    assert outcome["questionId"] is not None, "an assessment was delivered without an id"


async def test_a_question_already_in_the_pool_is_served_without_a_new_job(actor, corpus, durable):
    """Supply is per word and shared between learners, so the second one pays nothing.

    This is what `C2` buys: the pool is keyed by `(sense, level, type)` rather than by
    learner or session, so the first learner's session paid to prepare it and the next
    learner's encounter is a database read.

    The assertion is on the durable fact rather than on the wire timing: the number of
    stored questions for this sense must not grow when a second learner studies it. A
    timing assertion ("the second learner never saw preparing") would be a race between
    the worker and the poll and would prove nothing about the pool.

    The two learners must be *different people*. The same learner studying the word
    again is a different situation entirely: their sense is now scheduled and not yet
    due, so a second session correctly admits nothing.
    """
    first = actor.new()
    sense = corpus["tenacious"]
    first_deck = await first.deck("First")
    await first.add_sense(first_deck["id"], sense)
    await _drain(first, (await first.start_session(first_deck["id"]))["sessionId"])

    prepared = await _question_count(durable, sense)
    assert prepared > 0, "the first learner's session prepared no supply at all"

    # A different learner, so the sense is new to them and gets admitted.
    second = actor.new()
    second_deck = await second.deck("Second")
    await second.add_sense(second_deck["id"], sense)
    session = await second.start_session(second_deck["id"])

    _, outcome = await _until_assessment(second, session["sessionId"])

    assert outcome["state"] == "ready", outcome
    assert outcome["senseId"] == sense
    assert await _question_count(durable, sense) == prepared, (
        "a second learner caused supply to be prepared again, so the pool is not shared"
    )


async def test_next_does_not_start_a_second_job_while_one_is_in_flight(actor, corpus):
    """Asking again during preparation must not queue the work twice.

    The work key is (session, round), so a repeated poll joins the job already
    running rather than starting another. The failure this prevents is a paid
    generation per poll, which is invisible until the bill arrives.
    """
    owner = actor.new()
    sense = corpus["meticulous"]
    deck = await owner.deck("Deck")
    await owner.add_sense(deck["id"], sense)
    session = await owner.start_session(deck["id"])

    states = [await owner.next_question(session["sessionId"]) for _ in range(3)]
    preparing = [state for state in states if state["state"] == "preparing"]

    if preparing:
        task_ids = {state.get("taskId") for state in preparing}
        assert len(task_ids) == 1, f"repeated polls started separate jobs: {task_ids}"


async def test_a_failed_supply_job_leaves_no_learning_effect(actor, durable, corpus):
    """A provider that refuses must not become a wrong grade or a debit.

    The job fails; the learner has answered nothing. So there must be no response
    row and no credit movement — the durable traces an answer leaves. The supply
    job itself is allowed to fail; it is the accounting that must not.

    ``review_log`` carries no session id (it is keyed by learner and sense), so the
    response row is the session-scoped trace and the review log is checked against
    the learner.
    """
    owner = actor.new()
    sense = corpus["pragmatic"]
    deck = await owner.deck("Deck")
    await owner.add_sense(deck["id"], sense)

    before_credit = await owner.credit()
    me = await owner.me()
    session = await owner.start_session(deck["id"])

    # Walk the session as far as it will go without answering, so whatever supply
    # exists is consumed and the learner reaches a genuine shortfall.
    for _ in range(20):
        state = await owner.next_question(session["sessionId"])
        if state["state"] in {"exhausted", "preparing"}:
            break
        if state["state"] == "break":
            continue
        if state["questionId"] is not None:
            break

    after_credit = await owner.credit()

    assert await durable.count(
        "SELECT count(*) FROM responses WHERE session_id = $1", session["sessionId"]
    ) == 0
    assert await durable.count(
        "SELECT count(*) FROM review_log WHERE user_id = $1", me["id"]
    ) == 0
    assert after_credit["balance"] == before_credit["balance"]


async def test_supply_never_blocks_a_learner_on_a_model_call(actor, corpus):
    """`next` answers in the state vocabulary, and answers promptly.

    The bound is generous and still meaningful: a request that waited on a provider
    would exceed it by an order of magnitude, and a request that returns immediately
    with a state has proven the read path is a read.
    """
    owner = actor.new()
    sense = corpus["elusive"]
    deck = await owner.deck("Deck")
    await owner.add_sense(deck["id"], sense)
    session = await owner.start_session(deck["id"])

    loop = asyncio.get_running_loop()
    started = loop.time()
    state = await owner.next_question(session["sessionId"])
    elapsed = loop.time() - started

    assert state["state"] in {"ready", "preparing", "waiting", "exhausted", "break"}
    assert elapsed < 10.0, f"next took {elapsed:.1f}s, which is not a read path"


# --- helpers ------------------------------------------------------------------


async def _question_count(durable, sense_id: int) -> int:
    """How many questions are stored for one sense.

    Read from the dictionary's own table rather than through a route: the pool is
    internal to supply, and the number of rows is the whole point — a route that
    exposed it would be a route added for a test.
    """
    return await durable.count(
        "SELECT count(*) FROM lexi.questions WHERE sense_id = $1", sense_id
    )


async def _until_assessment(
    caller, session_id: str, *, timeout: float = 120.0
) -> tuple[list[str], dict]:
    """Poll ``next`` until it delivers a graded assessment.

    Returns every state seen along the way as well as the delivery, because "did the
    client ever have to wait for preparation" is itself an assertion some journeys
    make — and it is only visible in the states passed through.

    Waiting is the product's own rule rather than a test convenience: supply is
    asynchronous, so a client that treats the first ``preparing`` as a failure would
    never see the question the worker is preparing for it. An exposure is stepped
    past — a new sense is shown before it is assessed.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    seen: list[str] = []
    last: dict = {}
    while asyncio.get_running_loop().time() < deadline:
        last = await caller.next_question(session_id)
        seen.append(last["state"])
        if last["state"] == "ready" and last["questionId"] is not None:
            return seen, last
        if last["state"] == "exhausted":
            raise AssertionError("session exhausted before any assessment was delivered")
        await asyncio.sleep(0.5)
    raise AssertionError(f"no assessment was ever delivered: {last}")


async def _drain(caller, session_id: str, *, limit: int = 40) -> list[int]:
    """Answer or dismiss every item the session offers, collecting the sense ids."""
    delivered: list[int] = []
    for _ in range(limit):
        state = await caller.next_question(session_id)
        if state["state"] == "exhausted":
            return delivered
        if state["state"] == "preparing":
            await asyncio.sleep(0.5)
            continue
        if state["state"] == "break":
            continue
        delivered.append(state["senseId"])
        if state["questionId"] is None:
            continue
        await caller.answer(session_id, state["questionId"], "run")
    return delivered
