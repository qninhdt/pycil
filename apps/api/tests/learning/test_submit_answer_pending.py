"""The pending/LLM branch of `submit_answer`, and the compensation matrix around it.

`submit_answer` is the most intricate route in the repo: 190 lines whose `try` block
spans 143 of them, with two grading modes and three different ways an early return
must leave Redis. None of it had a test. `submit_answer` was never called from the
suite at all — the two flows that touch `/v1/answers` only ever reached the
rule-graded branch, because the fake reader's supply is level-1 `definition_mcq`,
which grades synchronously. Line coverage of `router.py` was 56%, with 623-713 —
the entire pending path plus the `except` compensation — at zero.

The compensation matrix is what makes the route safe to fail, and it is genuinely
three-valued:

- `committed`   a durable row exists, so reopening the delivery would let a retry
                double-insert it.
- `bind_held`   nothing was written *and* the same question is still the one on
                screen, so the bind must survive for the retry to work.
- neither       a real abort: release the claim so the sense returns in a later
                round instead of being stranded for the session.

Getting any of those backwards produces a different, worse bug, so each is asserted
by its observable Redis consequence rather than by the flag.
"""

from __future__ import annotations

import uuid

import fakeredis.aioredis as fake_aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.auth.deps import current_user
from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.content.deps import get_lexi_client
from pycil.content.models import DeckSense
from pycil.db import redis as redis_module
from pycil.db.session import get_session
from pycil.hierarchy import service as hierarchy_service
from pycil.hierarchy.models import NodeType
from pycil.learning import session_store
from pycil.learning.models import Response
from pycil.main import create_app
from tests.learning.fakes import RUBRIC_AT_EVERY_LEVEL, FakeLexiReader

# A free-text sense: `use_in_sentence` is the fake's LLM type, so evaluating it
# returns `status="pending"` and the route must take the deferred branch.
_LLM_SENSE = 501
# A rule-graded sense, for the contrast cases.
_RULE_SENSE = 502


class _FakeArqPool:
    def __init__(self, fail: bool = False):
        self.jobs: list[tuple] = []
        self.fail = fail

    async def enqueue_job(self, *args):
        if self.fail:
            raise RuntimeError("arq_unreachable")
        self.jobs.append(args)
        return None


@pytest_asyncio.fixture
async def llm_client(engine, monkeypatch):
    """The app wired to a fake Lexi whose supply is LLM-graded free text."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        owner = await _user(session, "pending-owner@example.com")
        deck = await hierarchy_service.create_node(
            session, owner.id, node_type=NodeType.DECK, name="free text deck"
        )
        session.add(DeckSense(node_id=deck.id, sense_id=_LLM_SENSE, position=0))
        await session.commit()

    reader = FakeLexiReader(types=RUBRIC_AT_EVERY_LEVEL)
    # A rubric type declared at the assessment floor, which is the level a new
    # sense's checkpoints actually request. The shipped set cannot reach this branch:
    # its only free-text type declares levels {3, 4}, acquisition requests level 1,
    # and the resolver only walks *down* — so every question the suite could obtain
    # graded synchronously. See `fakes.RUBRIC_AT_EVERY_LEVEL`.
    reader.add_supply(_LLM_SENSE, 1, "rubric_free_text", count=4)

    redis = fake_aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "_redis", redis)

    pool = _FakeArqPool()

    async def _fake_pool():
        return pool

    monkeypatch.setattr("pycil.learning.router.get_arq_pool", _fake_pool)

    async def override_session():
        async with factory() as s:
            yield s

    async def override_user() -> CurrentUser:
        return CurrentUser(id=owner.id, email=owner.email)

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[current_user] = override_user
    app.dependency_overrides[get_lexi_client] = lambda: reader
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, factory, owner, deck, reader, redis, pool


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _ready_checkpoint(client, session_id, limit=8):
    """Poll /next until an assessment question is delivered."""
    for _ in range(limit):
        res = await client.get(f"/v1/sessions/{session_id}/next")
        assert res.status_code == 200
        body = res.json()
        if body["state"] == "ready" and body["interactionMode"] == "assessment":
            return body
    raise AssertionError("no assessment checkpoint was delivered")


async def _start(client, deck):
    started = await client.post("/v1/sessions", json={"nodeId": str(deck.id)})
    assert started.status_code == 200
    return started.json()["sessionId"]


# --- the pending branch itself -----------------------------------------------


async def test_a_free_text_answer_is_deferred_rather_than_graded(llm_client):
    """The branch that was never executed by any test.

    A rule type returns `graded` with a verdict in the response. An LLM type must
    return `pending` with a task id instead, because the verdict does not exist yet
    and inventing one is what B6 was about.
    """
    client, factory, owner, deck, reader, redis, pool = llm_client
    session_id = await _start(client, deck)
    checkpoint = await _ready_checkpoint(client, session_id)
    assert checkpoint["renderFormat"] == "free_text"

    answered = await client.post(
        "/v1/answers",
        json={
            "sessionId": session_id,
            "questionId": checkpoint["questionId"],
            "answer": "I used the word in a sentence.",
        },
    )

    assert answered.status_code == 200
    body = answered.json()
    assert body["gradeStatus"] == "pending"
    assert body["taskId"] is not None
    assert body["renderFormat"] == "free_text"
    # No verdict is claimed for an answer nobody has graded yet.
    assert body.get("isCorrect") is None
    assert body.get("masteryBefore") is None
    assert body.get("masteryAfter") is None


async def test_the_pending_row_keeps_the_raw_answer_for_the_worker(llm_client):
    """The worker grades from `raw_answer`; a rule-graded row deliberately has none.

    This is also the column B4's purge used to null out from under a live lease.
    """
    client, factory, owner, deck, reader, redis, pool = llm_client
    session_id = await _start(client, deck)
    checkpoint = await _ready_checkpoint(client, session_id)

    await client.post(
        "/v1/answers",
        json={
            "sessionId": session_id,
            "questionId": checkpoint["questionId"],
            "answer": "the learner's own words",
        },
    )

    async with factory() as session:
        row = (
            await session.execute(
                select(Response).where(Response.session_id == session_id)
            )
        ).scalar_one()
    assert row.raw_answer == "the learner's own words"
    assert row.is_correct is None
    assert row.requested_level == 1
    assert row.render_format == "free_text"
    assert row.idempotency_key == f"{session_id}:{checkpoint['questionId']}"


async def test_the_sense_is_marked_awaiting_grade(llm_client):
    """Until the verdict lands the sense must not be offered again, or the learner
    answers the same checkpoint twice while the first is still being graded."""
    client, factory, owner, deck, reader, redis, pool = llm_client
    session_id = await _start(client, deck)
    checkpoint = await _ready_checkpoint(client, session_id)

    await client.post(
        "/v1/answers",
        json={
            "sessionId": session_id,
            "questionId": checkpoint["questionId"],
            "answer": "something",
        },
    )

    progress = await session_store.get_progress(redis, session_id, _LLM_SENSE)
    assert progress.awaiting_grade is True


async def test_a_grading_job_is_enqueued_for_the_created_task(llm_client):
    client, factory, owner, deck, reader, redis, pool = llm_client
    session_id = await _start(client, deck)
    checkpoint = await _ready_checkpoint(client, session_id)

    answered = await client.post(
        "/v1/answers",
        json={
            "sessionId": session_id,
            "questionId": checkpoint["questionId"],
            "answer": "something",
        },
    )
    task_id = answered.json()["taskId"]

    grading_jobs = [job for job in pool.jobs if job[0] == "grade_answer_task"]
    assert len(grading_jobs) == 1
    assert grading_jobs[0][1] == str(task_id)


async def test_a_failed_enqueue_still_returns_pending(llm_client, monkeypatch):
    """The durable row and the task are the contract; the arq enqueue is a wake-up.

    `reconcile_pending_grades` finds the row regardless, so failing the enqueue must
    not fail the request — the learner's answer is already safely recorded.
    """
    client, factory, owner, deck, reader, redis, _pool = llm_client
    failing = _FakeArqPool(fail=True)

    async def _fail_pool():
        return failing

    session_id = await _start(client, deck)
    checkpoint = await _ready_checkpoint(client, session_id)
    monkeypatch.setattr("pycil.learning.router.get_arq_pool", _fail_pool)

    answered = await client.post(
        "/v1/answers",
        json={
            "sessionId": session_id,
            "questionId": checkpoint["questionId"],
            "answer": "something",
        },
    )

    assert answered.status_code == 200
    assert answered.json()["gradeStatus"] == "pending"
    async with factory() as session:
        row = (
            await session.execute(
                select(Response).where(Response.session_id == session_id)
            )
        ).scalar_one()
    assert row.raw_answer == "something"


async def test_resubmitting_the_same_question_is_refused(llm_client):
    """Consume-once: the bind is cleared by the first submit, so a replay — a double
    click, a retried request — must not create a second pending row and a second paid
    LLM call."""
    client, factory, owner, deck, reader, redis, pool = llm_client
    session_id = await _start(client, deck)
    checkpoint = await _ready_checkpoint(client, session_id)
    payload = {
        "sessionId": session_id,
        "questionId": checkpoint["questionId"],
        "answer": "something",
    }

    first = await client.post("/v1/answers", json=payload)
    second = await client.post("/v1/answers", json=payload)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "question_not_issued_for_session"
    async with factory() as session:
        rows = (
            await session.execute(
                select(Response).where(Response.session_id == session_id)
            )
        ).scalars().all()
    assert len(rows) == 1


# --- the compensation matrix, at route level ---------------------------------


async def test_quota_rejection_keeps_the_question_on_screen(llm_client, monkeypatch):
    """`bind_held`. The one rejection where the learner may simply submit again.

    The consume-once CAS has already cleared `current_qid` by this point, so doing
    nothing would make the retry fail with `question_not_issued_for_session` — a
    session-desync code shown to someone who merely hit a rate limit, and one the
    client recovers from by discarding their typed answer.

    And not `restore_delivered` either: that reopens the whole delivery, so the sense
    would come back later as some *other* question while this one is still on screen.
    """
    client, factory, owner, deck, reader, redis, pool = llm_client
    session_id = await _start(client, deck)
    checkpoint = await _ready_checkpoint(client, session_id)
    qid = checkpoint["questionId"]

    async def _no_slot(*_args, **_kwargs):
        return False

    monkeypatch.setattr(session_store, "take_grading_slot", _no_slot)
    rejected = await client.post(
        "/v1/answers",
        json={"sessionId": session_id, "questionId": qid, "answer": "typed answer"},
    )

    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "answer_grading_quota_exceeded"
    # The same question is still the bound checkpoint: re-armed, not reopened.
    assert await session_store.get_delivered(redis, session_id, _LLM_SENSE) == qid
    # Still excluded, so the delivery was not rewound to hand out a different one.
    assert qid in await session_store.excluded_ids(redis, session_id, _LLM_SENSE)
    # Nothing durable was written.
    async with factory() as session:
        rows = (
            await session.execute(
                select(Response).where(Response.session_id == session_id)
            )
        ).scalars().all()
    assert rows == []


async def test_the_same_answer_succeeds_once_the_quota_recovers(llm_client, monkeypatch):
    """The promise the previous test's bind exists to keep."""
    client, factory, owner, deck, reader, redis, pool = llm_client
    session_id = await _start(client, deck)
    checkpoint = await _ready_checkpoint(client, session_id)
    qid = checkpoint["questionId"]
    payload = {"sessionId": session_id, "questionId": qid, "answer": "typed answer"}

    # Exhaust the real quota rather than stubbing it, so the recovery path is the
    # production one. `monkeypatch.undo()` would also revert the fixture's own Redis
    # patch and leave the session unreachable.
    real_take = session_store.take_grading_slot
    refuse = True

    async def _gated(*args, **kwargs):
        if refuse:
            return False
        return await real_take(*args, **kwargs)

    monkeypatch.setattr(session_store, "take_grading_slot", _gated)
    assert (await client.post("/v1/answers", json=payload)).status_code == 409

    refuse = False
    retried = await client.post("/v1/answers", json=payload)

    assert retried.status_code == 200
    assert retried.json()["gradeStatus"] == "pending"


async def test_a_failed_durable_write_refunds_the_grading_slot(llm_client, monkeypatch):
    """B10's other half. The slot is charged before the write, because the write is
    what commits the learner to an LLM call — so if the write fails the charge has to
    come back, or they paid for a grade that never happened and cannot retry until
    the window rolls."""
    client, factory, owner, deck, reader, redis, pool = llm_client
    session_id = await _start(client, deck)
    checkpoint = await _ready_checkpoint(client, session_id)

    from pycil.learning import service as learning_service

    async def _explode(*_args, **_kwargs):
        raise RuntimeError("durable_write_failed")

    monkeypatch.setattr(learning_service, "create_pending_response", _explode)

    with pytest.raises(RuntimeError, match="durable_write_failed"):
        await client.post(
            "/v1/answers",
            json={
                "sessionId": session_id,
                "questionId": checkpoint["questionId"],
                "answer": "something",
            },
        )

    # The quota key is back to zero taken slots rather than holding a phantom charge.
    quota = await redis.get(f"session:grading-quota:{owner.id}")
    assert quota is None or int(quota) == 0


async def test_an_aborted_answer_releases_the_claim(llm_client, monkeypatch):
    """Neither `committed` nor `bind_held`: a genuine abort.

    The claim is released and the sense returns in a later round, rather than being
    stranded for the rest of the session.
    """
    client, factory, owner, deck, reader, redis, pool = llm_client
    session_id = await _start(client, deck)
    checkpoint = await _ready_checkpoint(client, session_id)
    qid = checkpoint["questionId"]

    from pycil.learning import service as learning_service

    async def _explode(*_args, **_kwargs):
        raise RuntimeError("durable_write_failed")

    monkeypatch.setattr(learning_service, "create_pending_response", _explode)
    with pytest.raises(RuntimeError):
        await client.post(
            "/v1/answers",
            json={"sessionId": session_id, "questionId": qid, "answer": "x"},
        )

    # Reopened: no bind, and the id is no longer excluded, so the sense is
    # deliverable again instead of being wedged.
    assert await session_store.get_delivered(redis, session_id, _LLM_SENSE) is None
    assert qid not in await session_store.excluded_ids(redis, session_id, _LLM_SENSE)


async def test_a_committed_answer_is_not_reopened_by_a_later_failure(
    llm_client, monkeypatch
):
    """`committed`. Once the pending row is durable, a failure further down the route
    must NOT re-arm the bind — that would let a retry insert a second row for the
    same question and pay for a second LLM grade."""
    client, factory, owner, deck, reader, redis, pool = llm_client
    session_id = await _start(client, deck)
    checkpoint = await _ready_checkpoint(client, session_id)
    qid = checkpoint["questionId"]

    from pycil.tasks import service as task_service

    async def _explode(*_args, **_kwargs):
        raise RuntimeError("task_submission_failed")

    # Fails after `create_pending_response` has committed.
    monkeypatch.setattr(task_service, "submit_or_join", _explode)

    with pytest.raises(RuntimeError, match="task_submission_failed"):
        await client.post(
            "/v1/answers",
            json={"sessionId": session_id, "questionId": qid, "answer": "x"},
        )

    # The durable row exists...
    async with factory() as session:
        rows = (
            await session.execute(
                select(Response).where(Response.session_id == session_id)
            )
        ).scalars().all()
    assert len(rows) == 1
    # ...so the delivery must stay consumed: a retry cannot double-insert.
    assert await session_store.get_delivered(redis, session_id, _LLM_SENSE) is None
    retried = await client.post(
        "/v1/answers",
        json={"sessionId": session_id, "questionId": qid, "answer": "x"},
    )
    assert retried.status_code == 409
    async with factory() as session:
        rows = (
            await session.execute(
                select(Response).where(Response.session_id == session_id)
            )
        ).scalars().all()
    assert len(rows) == 1


# --- rejections that precede the bind ----------------------------------------


async def test_a_purged_question_reopens_the_checkpoint(llm_client, monkeypatch):
    """F14 at route level. The question is gone from Lexi, so the learner can never
    resubmit that id — the checkpoint has to be reopened here or the sense is
    undeliverable for the rest of the session."""
    client, factory, owner, deck, reader, redis, pool = llm_client
    session_id = await _start(client, deck)
    checkpoint = await _ready_checkpoint(client, session_id)
    qid = checkpoint["questionId"]

    async def _gone(_question_id):
        return None

    monkeypatch.setattr(reader, "get_question", _gone)

    rejected = await client.post(
        "/v1/answers",
        json={"sessionId": session_id, "questionId": qid, "answer": "x"},
    )

    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "question_not_available"
    # Reopened by scan, since a purged question carries no sense id to look up.
    assert await session_store.get_delivered(redis, session_id, _LLM_SENSE) is None
    assert qid not in await session_store.excluded_ids(redis, session_id, _LLM_SENSE)


async def test_answering_an_exposure_is_refused_and_reopens(llm_client):
    """An exposure is a flashcard, not a checkpoint. Submitting one is a client bug,
    and it must not consume the sense's real checkpoint."""
    client, factory, owner, deck, reader, redis, pool = llm_client
    session_id = await _start(client, deck)
    first = await client.get(f"/v1/sessions/{session_id}/next")
    body = first.json()
    assert body["interactionMode"] == "exposure"

    rejected = await client.post(
        "/v1/answers",
        json={
            "sessionId": session_id,
            "questionId": f"exposure:{_LLM_SENSE}",
            "answer": "x",
        },
    )

    # The wire type for questionId is an integer, so a non-integer exposure id is
    # refused by validation before it reaches the route.
    assert rejected.status_code in (409, 422)


async def test_another_learners_session_is_not_found(llm_client, monkeypatch):
    """Never confirm that someone else's session exists."""
    client, factory, owner, deck, reader, redis, pool = llm_client
    session_id = await _start(client, deck)
    checkpoint = await _ready_checkpoint(client, session_id)

    async with factory() as session:
        stranger = await _user(session, "pending-stranger@example.com")

    async def _stranger() -> CurrentUser:
        return CurrentUser(id=stranger.id, email=stranger.email)

    client._transport.app.dependency_overrides[current_user] = _stranger

    rejected = await client.post(
        "/v1/answers",
        json={
            "sessionId": session_id,
            "questionId": checkpoint["questionId"],
            "answer": "x",
        },
    )

    assert rejected.status_code == 404
    assert rejected.json()["error"]["code"] == "session_not_found"


async def test_an_unknown_session_is_not_found(llm_client):
    client, *_ = llm_client

    rejected = await client.post(
        "/v1/answers",
        json={"sessionId": uuid.uuid4().hex, "questionId": 1234, "answer": "x"},
    )

    assert rejected.status_code == 404


async def test_a_committed_answer_keeps_its_exclusion_and_awaiting_flag(
    llm_client, monkeypatch
):
    """The observable consequence of `committed`, isolated.

    The previous test showed a retry is refused, but that alone does not prove the
    guard works: `create_pending_response` upserts on `(user_id, idempotency_key)`,
    so the database refuses a duplicate row whether or not the route reopens the
    delivery. Removing `committed` therefore left the whole 398-test suite green.

    What actually differs is the Redis state. `restore_delivered` rewinds
    `last_round_used` and drops the question id from the exclusion set — so with the
    guard removed, a question whose grade is genuinely pending becomes deliverable
    again and the learner can be handed the very checkpoint a worker is being paid to
    grade. `awaiting_grade` stays set either way, which is why the wedge is silent:
    the sense is simultaneously marked "waiting for a verdict" and "free to serve".
    """
    client, factory, owner, deck, reader, redis, pool = llm_client
    session_id = await _start(client, deck)
    checkpoint = await _ready_checkpoint(client, session_id)
    qid = checkpoint["questionId"]

    from pycil.tasks import service as task_service

    async def _explode(*_args, **_kwargs):
        raise RuntimeError("task_submission_failed")

    # Fails after `create_pending_response` has committed and after
    # `set_awaiting_grade`, so `committed` is the only thing preventing a reopen.
    monkeypatch.setattr(task_service, "submit_or_join", _explode)
    with pytest.raises(RuntimeError, match="task_submission_failed"):
        await client.post(
            "/v1/answers",
            json={"sessionId": session_id, "questionId": qid, "answer": "x"},
        )

    # The id stays excluded: the delivery was NOT rewound, so this question cannot be
    # re-served while its grade is outstanding.
    assert qid in await session_store.excluded_ids(redis, session_id, _LLM_SENSE)
    progress = await session_store.get_progress(redis, session_id, _LLM_SENSE)
    assert progress.awaiting_grade is True
    # And `last_round_used` was not rewound below the current round.
    assert progress.last_round_used == await session_store.current_round(
        redis, session_id
    )
