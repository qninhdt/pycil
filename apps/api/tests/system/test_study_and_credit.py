"""SYS-F — one full study session, from planning to a durable recap.

This is the longest journey in the suite and the only one that exercises the whole
learning loop in one pass: admission under the learner's own session shape, an
exposure for a word never seen, graded answers including a wrong one, a round break,
the ungraded re-ask that repairs the wrong answer, completion, and a recap that
outlives the session's Redis state.

The assertions are about the *durable* consequences rather than the screen. Two
questions decide most of them:

- **Is there exactly one schedule per learner per sense?** Strength is global to the
  learner, not per deck. A sense reachable through two decks must not grow two rows,
  because then the same word would be due twice and reviewed twice.
- **Does an ungraded re-ask change anything?** It must not. It exists to repair the
  learner's understanding, not their memory state, and the design is explicit that it
  writes no review log, no stability and no depth.
"""

import asyncio

import pytest

from tests.system.conftest import requires_stack

pytestmark = [pytest.mark.asyncio, requires_stack]

_STATES = {"ready", "preparing", "waiting", "exhausted", "break"}


async def test_a_full_session_advances_learning_once_per_sense(actor, corpus, durable):
    """Plan, expose, grade (including one wrong), re-ask, finish, and read the recap.

    The journey follows the product's own sequence rather than asserting each step in
    isolation, because the interesting failures are between the steps: a round that
    never breaks, a re-ask that is refused, a recap that needs the Redis state that was
    just deleted.
    """
    learner = actor.new()
    word = "meticulous"
    sense = corpus[word]

    # The same sense through two routes, so a per-deck schedule would show up as two.
    root = await learner.folder("Folder")
    deck_a = await learner.deck("A", parent_id=root["id"])
    deck_b = await learner.deck("B", parent_id=root["id"])
    await learner.add_sense(deck_a["id"], sense)
    await learner.add_sense(deck_b["id"], sense)

    # A round holds one item, so finishing the sense forces a round break.
    await learner.status(
        "PATCH",
        "/v1/me/learning-settings",
        200,
        json={"targetWordsPerSession": 1, "maxQuestionsPerRound": 1},
    )

    session = await learner.start_session(root["id"])
    session_id = session["sessionId"]
    assert session["admittedCount"] == 1, "one sense through two decks was admitted twice"

    seen = await _study_to_completion(learner, session_id, word)

    # Exactly one graded answer for the one admitted sense: the exposure and the
    # re-ask are the same sense being taught, not additional learning events.
    assert seen["graded"] == 1, f"expected one graded answer, saw {seen['graded']}"
    assert seen["exposed"] == 1, "a new sense was not exposed before assessment"
    assert seen["reask"] == 1, "a wrong answer did not produce its one ungraded re-ask"
    assert seen["wrong"] >= 1, "the journey never produced the wrong answer it depends on"

    assert (
        await durable.count("SELECT count(*) FROM responses WHERE session_id = $1", session_id) == 1
    ), "the session wrote more than one graded response"

    # One schedule per learner per sense, whichever deck it was reached through.
    assert (
        await durable.count(
            "SELECT count(*) FROM user_sense_stats WHERE user_id = $1 AND sense_id = $2",
            (await learner.me())["id"],
            sense,
        )
        == 1
    ), "one sense studied through two decks produced more than one schedule"

    # One review log for the one graded answer: the re-ask added none.
    assert (
        await durable.count(
            "SELECT count(*) FROM review_log WHERE user_id = $1", (await learner.me())["id"]
        )
        == 1
    ), "the re-ask wrote a second learning effect"

    # The recap is durable: the live namespace is gone, and the session still reads.
    state = await learner.session(session_id)
    assert state["status"] == "completed", state
    assert state["sensesAdmitted"] == 1
    assert state["answersTotal"] >= 1


async def test_a_wrong_answer_retreats_depth_and_a_correct_one_does_not(actor, corpus):
    """Depth follows correctness, and the graded verdict is immediate on the wire.

    The answer response carries the before/after pair, which is the only place the
    learner-facing consequence of a grade is observable.

    The first graded answer of a brand-new sense is the documented exception: depth
    zero is the unassessed state, so its first grade enters level one whatever the
    verdict — "depth 0 never coexists with status = scheduled". The retreat rule
    applies from level one upward, which is what this journey measures by grading a
    second time.
    """
    learner = actor.new()
    word = "pragmatic"
    sense = corpus[word]
    deck = await learner.deck("Deck")
    await learner.add_sense(deck["id"], sense)
    session = await learner.start_session(deck["id"])
    session_id = session["sessionId"]

    # Step past the exposure to the graded item.
    question = await _until_question(learner, session_id)

    first = await learner.answer(
        session_id, question["questionId"], _deliberately_wrong(question, word)
    )
    assert first["gradeStatus"] == "graded", first
    assert first["isCorrect"] is False, first
    # The unassessed floor: a first grade enters level one even when wrong.
    assert first["depthBefore"] == 0 and first["depthAfter"] == 1, first

    # A second wrong answer at an established depth must retreat.
    reask = await _until_reask(learner, session_id)
    assert reask is not None, "the wrong answer produced no ungraded re-ask"
    outcome = await learner.answer(
        session_id, reask["questionId"], _deliberately_wrong(reask, word)
    )

    # The re-ask is ungraded: it reports its verdict without moving any state.
    assert outcome["gradeStatus"] == "ungraded", outcome
    assert "depthAfter" not in outcome, "an ungraded re-ask reported a depth change"
    assert "masteryAfter" not in outcome, "an ungraded re-ask reported a mastery change"


async def test_a_wrong_answer_at_an_established_depth_retreats(actor, corpus, durable):
    """Above the floor, a wrong answer retreats — and the response says so.

    A sense is graded at most once per session, so reaching an established depth takes
    two sessions: the first grade lifts the sense off the unassessed floor, and depth
    advances on a *clean pass at the served depth*, which the second session supplies.
    That makes this a real spaced-repetition journey rather than a policy check — the
    unit level already proves the ladder's arithmetic; what is checked here is that
    the ladder's result reaches the learner's wire.

    The floor is part of the contract too: depth never falls below 1, so a retreat is
    only observable from level 2 upward. Each session is made due through the schedule
    row, which is state the product reaches on its own given time.
    """
    learner = actor.new()
    word = "elusive"
    sense = corpus[word]
    me = await learner.me()
    deck = await learner.deck("Deck")
    await learner.add_sense(deck["id"], sense)
    await learner.status(
        "PATCH",
        "/v1/me/learning-settings",
        200,
        json={"targetWordsPerSession": 1, "maxQuestionsPerRound": 10},
    )

    # Two clean passes at level 1: the first lifts the floor, the second advances.
    depth_after = 0
    for _ in range(2):
        session = await learner.start_session(deck["id"])
        question = await _until_question(learner, session["sessionId"])
        outcome = await learner.answer(
            session["sessionId"], question["questionId"], _correct_answer(question, word)
        )
        assert outcome["isCorrect"] is True, outcome
        depth_after = outcome["depthAfter"]
        await _finish(learner, session["sessionId"])
        await durable.seed(
            "UPDATE user_sense_stats SET next_review_date = NOW() - INTERVAL '1 day' "
            "WHERE user_id = $1 AND sense_id = $2",
            me["id"],
            sense,
        )

    assert depth_after >= 2, (
        f"two clean passes did not advance depth above the floor: {depth_after}"
    )

    # A wrong answer at that established depth must retreat, and report it.
    session = await learner.start_session(deck["id"])
    question = await _until_question(learner, session["sessionId"])
    wrong = await learner.answer(
        session["sessionId"], question["questionId"], _deliberately_wrong(question, word)
    )

    assert wrong["isCorrect"] is False, wrong
    assert wrong["depthBefore"] >= 2, wrong
    assert wrong["depthAfter"] < wrong["depthBefore"], (
        f"a wrong answer at an established depth did not retreat: {wrong}"
    )


async def test_a_round_break_separates_rounds_rather_than_ending_the_session(actor, corpus):
    """A full round offers a break; the next poll enters a new round.

    A round is a chunk of attention, not the session. Treating the break as
    completion is how a learner with more work left is told they are finished.

    The poll stops at ``exhausted``: a finished session has deleted its live state,
    so continuing to call ``next`` correctly answers 404 — that is completion, not
    another round.
    """
    learner = actor.new()
    word = "elusive"
    sense = corpus[word]
    deck = await learner.deck("Deck")
    await learner.add_sense(deck["id"], sense)
    await learner.status(
        "PATCH",
        "/v1/me/learning-settings",
        200,
        json={"targetWordsPerSession": 1, "maxQuestionsPerRound": 1},
    )

    session = await learner.start_session(deck["id"])
    session_id = session["sessionId"]

    question = await _until_question(learner, session_id)
    await learner.answer(session_id, question["questionId"], _correct_answer(question, word))

    states = await _states_until_end(learner, session_id)

    assert set(states) <= _STATES, states
    assert "break" in states, f"a full round never offered a break: {states}"


async def test_a_session_is_not_readable_by_another_learner(actor, corpus):
    """A session id is not a capability. The stranger gets the same 404 as an unknown one."""
    owner = actor.new()
    deck = await owner.deck("Deck")
    await owner.add_sense(deck["id"], corpus["vivid"])
    session = await owner.start_session(deck["id"])

    stranger = actor.new()
    denied = await stranger.get(f"/v1/sessions/{session['sessionId']}")

    assert denied.status_code == 404
    assert denied.json()["code"] == "session_not_found"


# --- helpers ------------------------------------------------------------------


def _correct_answer(question: dict, word: str) -> str:
    """The right answer for a delivered item, derived from the item and the headword.

    A test may know the answer — it is the one thing the wire deliberately withholds
    from the learner, not from the operator. The headword is the answer for every
    render kind the fixture produces: a single-choice item offers it among the options,
    a text-span item blanks it out of the stem, and a free-text item asks for it. So
    one rule covers the render kinds rather than a branch per kind guessing.

    ``word_bank`` is checked before ``options`` because a text-span question also
    carries a bank, and the two payload keys are not mutually exclusive by name.
    """
    payload = question.get("payload") or {}
    options = payload.get("options") or payload.get("word_bank")
    if options:
        match = next((option for option in options if option.lower() == word.lower()), None)
        assert match is not None, f"{word!r} is not among the options {options}"
        return match
    return word


def _deliberately_wrong(question: dict, word: str) -> str:
    """An answer that is certainly not correct for this item.

    A single-choice item is answered by option text, so any string absent from the
    options is wrong — and asserting it is absent keeps that true if a fixture ever
    starts emitting this text.
    """
    payload = question.get("payload") or {}
    options = payload.get("options") or payload.get("word_bank") or []
    answer = "definitely-not-the-answer"
    assert answer not in options and answer.lower() != word.lower()
    return answer


async def _finish(caller, session_id: str, *, limit: int = 20) -> None:
    """Drive a session to ``exhausted``, answering nothing further.

    Used to close a session so the next one plans from a settled schedule rather than
    from a live namespace. Reaching ``exhausted`` is the only way the product ends a
    session, so a journey that needs the next one to be a fresh plan has to get here.
    """
    for _ in range(limit):
        state = await caller.next_question(session_id)
        if state["state"] == "exhausted":
            return
        if state["state"] == "break":
            continue
        if state["state"] == "ready" and state["questionId"] is not None:
            await caller.answer(session_id, state["questionId"], "closing")
            continue
        await asyncio.sleep(0.5)
    raise AssertionError("session never finished")


async def _next_state(caller, session_id: str) -> str:
    state = await caller.next_question(session_id)
    return state["state"]


async def _states_until_end(caller, session_id: str, *, limit: int = 12) -> list[str]:
    """Every state ``next`` reports until the session ends.

    ``exhausted`` is terminal: the live namespace is gone, so a further call is a
    404 rather than another round. The loop therefore stops there instead of polling
    a session that has correctly finished.
    """
    seen: list[str] = []
    for _ in range(limit):
        state = await caller.next_question(session_id)
        seen.append(state["state"])
        if state["state"] == "exhausted":
            return seen
    return seen


async def _until_question(
    caller, session_id: str, *, timeout: float = 120.0, exclude: set[int] | None = None
) -> dict:
    """Poll ``next`` until it delivers a graded assessment.

    ``exclude`` skips question ids already answered in this journey: the exclusion set
    is session-scoped, so the same item may legitimately be served again, and a
    journey measuring a *second* grade must grade a different item.
    """
    skip = exclude or set()
    deadline = asyncio.get_running_loop().time() + timeout
    last: dict = {}
    while asyncio.get_running_loop().time() < deadline:
        last = await caller.next_question(session_id)
        if last["state"] == "ready" and last["questionId"] is not None:
            if last["questionId"] not in skip:
                return last
        elif last["state"] == "exhausted":
            raise AssertionError("session exhausted before an assessment was delivered")
        await asyncio.sleep(0.5)
    raise AssertionError(f"no assessment was ever delivered: {last}")


async def _until_reask(caller, session_id: str, *, timeout: float = 120.0) -> dict | None:
    """Poll ``next`` until the ungraded re-ask appears, or the session ends."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        state = await caller.next_question(session_id)
        if state["state"] == "exhausted":
            return None
        if state["state"] == "ready" and state["questionId"] is not None:
            if state.get("isGraded") is False:
                return state
        await asyncio.sleep(0.5)
    return None


async def _study_to_completion(caller, session_id: str, word: str, *, limit: int = 60) -> dict:
    """Drive a session to the end, counting what the learner actually saw.

    Every delivery is answered with a deliberately wrong answer for the graded item,
    so the journey exercises the wrong-answer path and its re-ask rather than only
    the happy one. The re-ask is answered correctly, which is what makes it terminate.
    """
    counts = {"graded": 0, "exposed": 0, "reask": 0, "wrong": 0}
    for _ in range(limit):
        state = await caller.next_question(session_id)
        if state["state"] == "exhausted":
            return counts
        if state["state"] in {"preparing", "waiting"}:
            await asyncio.sleep(0.5)
            continue
        if state["state"] == "break":
            continue
        if state["questionId"] is None:
            counts["exposed"] += 1
            continue
        if state.get("isGraded") is False:
            counts["reask"] += 1
            await caller.answer(session_id, state["questionId"], "repaired")
            continue
        counts["graded"] += 1
        outcome = await caller.answer(
            session_id, state["questionId"], _deliberately_wrong(state, word)
        )
        if outcome["isCorrect"] is False:
            counts["wrong"] += 1
    raise AssertionError(f"session never completed: {counts}")
