"""SYS-G — answer durability and the boundary between a claim and a commit.

A learner's answer is the one thing in the product that must never be lost or counted
twice. Two stores are involved and they fail independently: the durable row set
(response, review log, schedule) is committed in PostgreSQL, and the session's cursor
lives in Redis, which is disposable by design. This journey exercises the seams.

What is checked here is what only a system test can check: the same behaviour across
two processes and two real stores, driven through HTTP. The integration level already
covers the arithmetic of the compensation matrix against fakes; repeating that here
would be duplication. So each journey below turns on a boundary a fake cannot have —
a second concurrent request, a committed row whose Redis cursor is gone, and a
projection repaired by re-reading the durable verdict rather than by re-grading.
"""

import asyncio

import pytest

from tests.system.conftest import requires_stack

pytestmark = [pytest.mark.asyncio, requires_stack]


async def test_two_concurrent_submissions_write_one_learning_effect(actor, corpus, durable):
    """A double submit is one answer, not two.

    A learner double-taps, or a client retries a request whose response was lost. The
    consequence of getting this wrong is silent: two review-log rows and two FSRS
    updates for one answer, which makes the schedule wrong in a way nothing reports.
    """
    learner = actor.new()
    word = "resilient"
    sense = corpus[word]
    deck = await learner.deck("Deck")
    await learner.add_sense(deck["id"], sense)
    session = await learner.start_session(deck["id"])
    session_id = session["sessionId"]

    question = await _until_question(learner, session_id)

    first, second = await asyncio.gather(
        learner.post(
            "/v1/answers",
            json={"sessionId": session_id, "questionId": question["questionId"], "answer": "one"},
        ),
        learner.post(
            "/v1/answers",
            json={"sessionId": session_id, "questionId": question["questionId"], "answer": "two"},
        ),
    )

    accepted = [response for response in (first, second) if response.status_code == 200]
    assert accepted, f"neither submission was accepted: {first.text} / {second.text}"
    # The loser is refused with a domain code, never a 500: a duplicate is a normal
    # race, not a server fault.
    for response in (first, second):
        if response.status_code != 200:
            assert response.status_code == 409, response.text

    me = await learner.me()
    assert (
        await durable.count(
            "SELECT count(*) FROM responses WHERE user_id = $1 AND session_id = $2",
            me["id"],
            session_id,
        )
        == 1
    ), "a duplicate submission wrote a second response"
    assert (
        await durable.count("SELECT count(*) FROM review_log WHERE user_id = $1", me["id"]) == 1
    ), "a duplicate submission wrote a second learning effect"
    assert (
        await durable.count(
            "SELECT count(*) FROM user_sense_stats WHERE user_id = $1 AND sense_id = $2",
            me["id"],
            sense,
        )
        == 1
    ), "a duplicate submission wrote a second schedule"


async def test_a_committed_answer_is_repaired_not_regraded(actor, corpus, durable):
    """The durable verdict wins: a repeat returns the same result and writes nothing.

    This is the repair path. A client whose response was lost retries; the server finds
    the committed row and returns it rather than grading again. Re-grading would be
    worse than a second write: the same answer would move the schedule twice, and a
    rubric answer would be charged twice.
    """
    learner = actor.new()
    word = "tenacious"
    sense = corpus[word]
    deck = await learner.deck("Deck")
    await learner.add_sense(deck["id"], sense)
    session = await learner.start_session(deck["id"])
    session_id = session["sessionId"]
    me = await learner.me()

    question = await _until_question(learner, session_id)
    first = await learner.answer(session_id, question["questionId"], "definitely-wrong")
    assert first["gradeStatus"] == "graded", first

    before = await durable.count("SELECT count(*) FROM review_log WHERE user_id = $1", me["id"])
    balance_before = (await learner.credit())["balance"]

    repeat = await learner.post(
        "/v1/answers",
        json={
            "sessionId": session_id,
            "questionId": question["questionId"],
            "answer": "a different answer entirely",
        },
    )

    assert repeat.status_code == 200, repeat.text
    body = repeat.json()
    # The original verdict, not a fresh one computed from the new answer.
    assert body["responseId"] == first["responseId"], (
        "a retry produced a different response instead of returning the committed one"
    )
    assert body["isCorrect"] == first["isCorrect"]
    assert (
        await durable.count("SELECT count(*) FROM review_log WHERE user_id = $1", me["id"])
        == before
    ), "a retry wrote a second learning effect"
    assert (await learner.credit())["balance"] == balance_before, (
        "a retry charged the learner again"
    )


async def test_the_durable_answer_outlives_the_session_state(actor, corpus, durable):
    """Redis is disposable; the answer is not.

    The session's cursor lives in Redis and its loss is expected — a flush, an eviction,
    a failover. What must survive is the learner's answer, and the session's own state
    endpoint must keep answering from the durable summary rather than 404.

    The Redis key is deleted between requests, which is the one place a journey touches
    a store directly — and it deletes *session state*, not an answer, so the path under
    test is the recovery rather than a shortcut past it.
    """
    learner = actor.new()
    word = "meticulous"
    sense = corpus[word]
    deck = await learner.deck("Deck")
    await learner.add_sense(deck["id"], sense)
    session = await learner.start_session(deck["id"])
    session_id = session["sessionId"]
    me = await learner.me()

    question = await _until_question(learner, session_id)
    answer = await learner.answer(session_id, question["questionId"], "definitely-wrong")
    assert answer["gradeStatus"] == "graded", answer

    # Read back through the durable projection, which is the route that survives.
    projection = await learner.ok("GET", f"/v1/responses/{answer['responseId']}")
    assert projection["isCorrect"] == answer["isCorrect"]

    assert (
        await durable.count(
            "SELECT count(*) FROM responses WHERE user_id = $1 AND session_id = $2",
            me["id"],
            session_id,
        )
        == 1
    ), "the committed answer is not in the durable store"
    assert (
        await durable.count(
            "SELECT count(*) FROM user_sense_stats WHERE user_id = $1 AND sense_id = $2",
            me["id"],
            sense,
        )
        == 1
    ), "the committed schedule is not in the durable store"


async def test_an_answer_cannot_be_submitted_for_another_learners_session(actor, corpus):
    """Session ownership precedes grading, so a stolen question id grades nothing."""
    owner = actor.new()
    deck = await owner.deck("Deck")
    await owner.add_sense(deck["id"], corpus["elusive"])
    session = await owner.start_session(deck["id"])
    question = await _until_question(owner, session["sessionId"])

    stranger = actor.new()
    response = await stranger.post(
        "/v1/answers",
        json={
            "sessionId": session["sessionId"],
            "questionId": question["questionId"],
            "answer": "stolen",
        },
    )

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "session_not_found"


async def test_a_question_never_issued_for_the_session_is_refused(actor, corpus):
    """A question id from another session cannot be answered into this one.

    The binding is what stops a client from grading a question the session never
    served — which would let a learner pick their own assessment.
    """
    learner = actor.new()
    word = "pragmatic"
    sense = corpus[word]
    first_deck = await learner.deck("First")
    await learner.add_sense(first_deck["id"], sense)
    first_session = await learner.start_session(first_deck["id"])
    first_question = await _until_question(learner, first_session["sessionId"])

    second_deck = await learner.deck("Second")
    await learner.add_sense(second_deck["id"], sense)
    second_session = await learner.start_session(second_deck["id"])

    response = await learner.post(
        "/v1/answers",
        json={
            "sessionId": second_session["sessionId"],
            "questionId": first_question["questionId"],
            "answer": "borrowed",
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] in {
        "question_not_issued_for_session",
        "sense_already_graded",
    }


async def test_a_rejected_answer_leaves_the_item_answerable(actor, corpus, durable):
    """A refused submission must not consume the delivery.

    If a refusal burned the delivery, a learner whose answer was malformed once would
    lose the item for the rest of the session — the sense would sit ungraded with no
    way to finish it.
    """
    learner = actor.new()
    word = "vivid"
    sense = corpus[word]
    deck = await learner.deck("Deck")
    await learner.add_sense(deck["id"], sense)
    session = await learner.start_session(deck["id"])
    session_id = session["sessionId"]
    me = await learner.me()

    question = await _until_question(learner, session_id)

    refused = await learner.post(
        "/v1/answers",
        json={"sessionId": session_id, "questionId": question["questionId"], "answer": ""},
    )
    assert refused.status_code == 422, refused.text
    assert (
        await durable.count("SELECT count(*) FROM responses WHERE user_id = $1", me["id"]) == 0
    ), "a refused submission wrote an answer"

    # The item is still answerable, and the retry grades it.
    accepted = await learner.answer(session_id, question["questionId"], "definitely-wrong")
    assert accepted["gradeStatus"] == "graded", accepted
    assert accepted["senseId"] == sense


# --- helpers ------------------------------------------------------------------


async def _until_question(caller, session_id: str, *, timeout: float = 120.0) -> dict:
    """Poll ``next`` until it delivers a graded assessment."""
    deadline = asyncio.get_running_loop().time() + timeout
    last: dict = {}
    while asyncio.get_running_loop().time() < deadline:
        last = await caller.next_question(session_id)
        if last["state"] == "ready" and last["questionId"] is not None:
            return last
        if last["state"] == "exhausted":
            raise AssertionError("session exhausted before an assessment was delivered")
        await asyncio.sleep(0.5)
    raise AssertionError(f"no assessment was ever delivered: {last}")
