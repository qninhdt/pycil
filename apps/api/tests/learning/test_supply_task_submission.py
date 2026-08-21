"""Supply is a durable task the client can subscribe to, not a poll target.

`/next` mutates — it advances rounds, reserves deliveries and extends the
exclusion set — so a client that re-calls it while waiting for supply is
re-running a mutation for no reason. The fix is to give the wait something to
listen to: the request goes through the task registry, so a task row and a live
interest exist and `async:{task_id}` becomes a channel the subscribe proxy will
admit.

What is asserted here is the seam, not the wire: that a request creates exactly
one task per session-round, that a second request in the same round *joins* it
rather than buying a second generation, and that the two pre-existing bounds are
untouched. The bounds matter most — the event changes how completion is
announced, never how much generation a session may pay for.
"""

import uuid

import fakeredis.aioredis as fake_aioredis
import pytest

from pycil.auth.models import User
from pycil.learning.application import session_flow
from pycil.learning.infra import session_store
from pycil.tasks.domain.vocabulary import (
    JOB_NAME_FOR_KIND,
    TASK_KIND_QUESTION_SUPPLY,
    SupplyDispatch,
)
from pycil.tasks.domain.work_keys import supply_work_key
from pycil.tasks.infra.models import AsyncTask

pytestmark = pytest.mark.asyncio


class _Pool:
    """Records what was enqueued, so a duplicate job is visible rather than implied."""

    def __init__(self) -> None:
        self.jobs: list[tuple] = []

    async def enqueue_job(self, *args):
        self.jobs.append(args)


@pytest.fixture
def pool(monkeypatch) -> _Pool:
    recorder = _Pool()

    async def get_pool():
        return recorder

    monkeypatch.setattr(session_flow, "get_arq_pool", get_pool)
    return recorder


async def _owner(session) -> uuid.UUID:
    """A real user row: the interest holds a foreign key to it.

    A fabricated UUID makes `submit_or_join` fail its insert, and the failure is
    indistinguishable from the command replay it retries for — so it spends all four
    attempts and raises `async_command_conflict`, which looks nothing like the
    missing row that caused it.
    """
    user = User(email=f"supply-{uuid.uuid4().hex[:8]}@example.com")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user.id


async def _live_session(owner_id: uuid.UUID) -> tuple[fake_aioredis.FakeRedis, str]:
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    session_id = uuid.uuid4().hex
    await session_store.create(
        redis,
        session_id,
        owner_id=owner_id,
        node_id=uuid.uuid4(),
        scope_generation=1,
        target_words=3,
        max_per_round=4,
        admitted=[],
    )
    return redis, session_id


async def test_a_supply_request_creates_a_task_the_client_can_subscribe_to(session, pool):
    owner_id = await _owner(session)
    redis, session_id = await _live_session(owner_id)

    result = await session_flow.request_supply(
        session,
        redis,
        session_id=session_id,
        owner_id=owner_id,
        round_index=1,
        demands=[(11, 1, 2)],
    )

    assert result.state == "requested"
    # Without an id the client has no channel and falls back to re-calling `/next`,
    # which is the mutating poll this exists to remove.
    assert result.task_id is not None

    task = await session.get(AsyncTask, result.task_id)
    assert task is not None
    assert task.kind == TASK_KIND_QUESTION_SUPPLY
    assert task.work_key == supply_work_key(session_id, 1)
    # The reconciler re-enqueues from `dispatch` alone, so anything missing here is
    # a task that can never be recovered once its enqueue is lost.
    assert task.dispatch == SupplyDispatch(
        owner_id=str(owner_id),
        session_id=session_id,
        round_index=1,
        demands=[(11, 1, 2)],
    ).to_dispatch()
    assert pool.jobs == [
        (
            JOB_NAME_FOR_KIND[TASK_KIND_QUESTION_SUPPLY],
            str(task.id),
            str(owner_id),
            [(11, 1, 2)],
        )
    ]


async def test_two_requests_in_one_round_join_one_task_rather_than_buying_two(session, pool):
    """The work key's whole job, asserted directly.

    The demand list is derived from what the round still has unresolved, so two
    `/next` calls in the same round can compute *different* lists — the first
    consumes a delivery the second no longer sees. Keying on the demands would make
    those two separate tasks: the learner pays for generation twice, and the client
    subscribes to whichever id it happened to see last while the other runs unwatched.

    Note the second call arrives inside the cooldown, which is the realistic case —
    a reload re-establishes the wait seconds later. The running task is reported
    anyway, because the cooldown governs *starting* generation and has nothing to
    say about work already paid for. Answering `cooling` with no id would send the
    client back to polling while its questions were being written.
    """
    owner_id = await _owner(session)
    redis, session_id = await _live_session(owner_id)

    first = await session_flow.request_supply(
        session, redis, session_id=session_id, owner_id=owner_id,
        round_index=1, demands=[(11, 1, 2), (12, 1, 1)],
    )
    # A different demand list, as a real second call in the same round would compute.
    second = await session_flow.request_supply(
        session, redis, session_id=session_id, owner_id=owner_id,
        round_index=1, demands=[(12, 1, 1)],
    )

    assert first.task_id == second.task_id
    assert second.state == "requested"
    # Joined, not re-enqueued: the second call must not buy a second generation.
    assert len(pool.jobs) == 1


async def test_a_later_round_gets_its_own_task(session, pool):
    """Rounds are separate work, so joining across them would strand the second."""
    owner_id = await _owner(session)
    redis, session_id = await _live_session(owner_id)

    first = await session_flow.request_supply(
        session, redis, session_id=session_id, owner_id=owner_id,
        round_index=1, demands=[(11, 1, 2)],
    )
    # Cleared because the cooldown is per session, not per round: without this the
    # second round would be told to wait, which is a real behaviour but not the one
    # under test here.
    await redis.hset(session_store._key(session_id), "prepare_retry_at", "0")
    second = await session_flow.request_supply(
        session, redis, session_id=session_id, owner_id=owner_id,
        round_index=2, demands=[(11, 1, 2)],
    )

    assert first.task_id != second.task_id
    assert len(pool.jobs) == 2


async def test_the_per_session_spend_bound_survives_the_move_to_tasks(session, pool):
    """`claim_prepare_attempt` caps generation spend; the event does not replace it.

    It is the only producer of `question_preparation_exhausted`, and it is easy to
    mistake for a poll limiter now that the poll is gone. Exhaustion must still
    arrive after the same three attempts, and must start no task — a task implies
    work is coming, and here none is.
    """
    owner_id = await _owner(session)
    redis, session_id = await _live_session(owner_id)

    for attempt in range(3):
        result = await session_flow.request_supply(
            session, redis, session_id=session_id, owner_id=owner_id,
            round_index=attempt, demands=[(11, 1, 2)],
        )
        assert result.state == "requested"
        # The cooldown is per session, so it has to be cleared to reach the ceiling
        # rather than the cooldown on each subsequent call.
        await redis.hset(session_store._key(session_id), "prepare_retry_at", "0")

    spent = await session_flow.request_supply(
        session, redis, session_id=session_id, owner_id=owner_id,
        round_index=4, demands=[(11, 1, 2)],
    )
    assert spent.state == "exhausted"
    assert spent.task_id is None
    assert len(pool.jobs) == 3


async def test_a_cooling_request_starts_no_task_and_offers_nothing_to_watch(session, pool):
    """Null is "ask again shortly", and the client's fallback depends on it.

    A task id here would be a lie the client acts on: it would subscribe and wait
    for an event no worker will ever publish, and the session would hang where it
    previously recovered on the next call.

    A *later* round on purpose. The same round would find the running task and
    report it, which is the join above; this is the case where the cooldown blocks
    genuinely new work and there is nothing yet to watch.
    """
    owner_id = await _owner(session)
    redis, session_id = await _live_session(owner_id)

    await session_flow.request_supply(
        session, redis, session_id=session_id, owner_id=owner_id,
        round_index=1, demands=[(11, 1, 2)],
    )
    cooling = await session_flow.request_supply(
        session, redis, session_id=session_id, owner_id=owner_id,
        round_index=2, demands=[(11, 1, 2)],
    )

    assert cooling.state == "cooling"
    assert cooling.task_id is None
    assert len(pool.jobs) == 1


async def test_a_lost_enqueue_still_leaves_a_recoverable_task(session, monkeypatch):
    """The enqueue is best-effort *because* the row is durable.

    Before the registry, a failed enqueue meant the supply request was simply gone
    and the next `/next` re-requested it. Now the client is subscribed and no longer
    re-asks, so the committed row plus the reconciler is the entire recovery path.
    """
    owner_id = await _owner(session)
    redis, session_id = await _live_session(owner_id)

    async def broken_pool():
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(session_flow, "get_arq_pool", broken_pool)

    result = await session_flow.request_supply(
        session, redis, session_id=session_id, owner_id=owner_id,
        round_index=1, demands=[(11, 1, 2)],
    )

    assert result.state == "requested"
    task = await session.get(AsyncTask, result.task_id)
    assert task is not None, "the enqueue failed and took the task with it"
    assert task.dispatch["demands"] == [[11, 1, 2]]


async def test_a_spent_generation_slot_still_reports_work_already_running(
    session, pool, monkeypatch
):
    """The slot bounds new generation, and says nothing about work already bought.

    This is the reload case, and it is the one that decides whether the event is an
    improvement or a regression. The learner refreshes mid-generation: `/next`
    recomputes the same demands, the per-learner slot is spent, and before this the
    answer was `no_slot` -> `preparing` with a null id. The client reads null as
    "nothing to subscribe to" and polls until its budget stalls — while the task it
    should have been watching completes without an audience.

    So the live task is looked up first, ahead of both bounds. Asserted by spending
    the slot outright rather than by timing, so the test states the rule rather than
    reproducing one schedule of it.
    """
    owner_id = await _owner(session)
    redis, session_id = await _live_session(owner_id)

    started = await session_flow.request_supply(
        session, redis, session_id=session_id, owner_id=owner_id,
        round_index=1, demands=[(11, 1, 2)],
    )
    assert started.task_id is not None

    async def slot_refused(*args, **kwargs):
        return False

    monkeypatch.setattr(session_store, "take_generation_slot", slot_refused)

    rejoined = await session_flow.request_supply(
        session, redis, session_id=session_id, owner_id=owner_id,
        round_index=1, demands=[(11, 1, 2)],
    )

    assert rejoined.state == "requested"
    assert rejoined.task_id == started.task_id, (
        "a spent slot hid a running task, so the client gets no channel and returns "
        "to polling while its questions are being written"
    )
    assert len(pool.jobs) == 1
