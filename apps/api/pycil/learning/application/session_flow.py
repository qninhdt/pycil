"""Session lifecycle and the question-delivery loop.

Extracted from the router, which mixed four concerns in one file. What lives here is
everything between "the learner asked for a session" and "here is the next question":
planning under a structural-generation retry, the quota-gated supply warm-up, and the
round-walking loop that either delivers a question or explains why it cannot.

The supply request appears twice in the flow — once eagerly at session start and once
when a round resolves nothing — and both copies carried the same quota gate, the same
cooldown claim and the same swallowed enqueue failure. `request_supply` is that one
policy, stated once: a slot, then an attempt, then a best-effort enqueue.

The delivery outcome is returned as data rather than as a response model, so the
scheduling decisions are testable without HTTP and the router stays responsible only
for turning them into wire shapes.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ConflictError, NotFoundError, ServiceUnavailableError
from pycil.hierarchy.application.access import require_node_access
from pycil.hierarchy.infra.models import Node
from pycil.learning.application import (
    planning,
    round_scheduler,
    session_recap,
)
from pycil.learning.domain import resolver
from pycil.learning.domain.resolver import ResolvedQuestion
from pycil.learning.infra import session_store
from pycil.ports.lexi import LexiReader
from pycil.tasks.application import service as task_service
from pycil.tasks.application.dispatch import submit_and_dispatch
from pycil.tasks.domain.vocabulary import TASK_KIND_QUESTION_SUPPLY, SupplyDispatch
from pycil.tasks.domain.work_keys import supply_work_key

# How many times session creation re-plans when a structural mutation lands mid-flight.
_PLAN_ATTEMPTS = 2


@dataclass(frozen=True)
class StartedSession:
    session_id: str
    node_id: UUID
    admitted_count: int
    expires_at: datetime
    has_work: bool


@dataclass(frozen=True)
class Delivered:
    """A question is ready to serve."""

    resolved: ResolvedQuestion


@dataclass(frozen=True)
class RoundBreak:
    """The round is full or its remaining work waits for a later one."""

    round_index: int


@dataclass(frozen=True)
class NoQuestionYet:
    """Nothing to serve right now, and why.

    ``preparing``  supply was requested, or another request took the candidate.
    ``waiting``    open work exists but nothing is servable this instant.
    ``exhausted``  the session is complete; the recap is written and Redis is gone.

    ``supply_task_id`` is the durable task the client subscribes to instead of
    asking again, and it is set only on ``preparing`` — and not always even then.
    A request refused by the per-learner slot or still inside its cooldown starts
    no task, so there is nothing to subscribe to and the client keeps its bounded
    fallback for exactly that case. `None` therefore means "ask again shortly",
    not "no supply is coming".
    """

    reason: Literal["preparing", "waiting", "exhausted"]
    supply_task_id: UUID | None = None


DeliveryOutcome = Delivered | RoundBreak | NoQuestionYet


async def start(
    session: AsyncSession,
    redis: Redis,
    *,
    user: CurrentUser,
    node_id: UUID,
    now: datetime | None = None,
) -> StartedSession:
    """Plan and create one session, then warm supply for it best-effort.

    Session shape is the learner's rather than the node's, so it is resolved once
    here instead of per node kind: a folder session and a deck session get the same
    shape, which is what the settings form promises.
    """
    moment = now if now is not None else datetime.now(UTC)
    session_id = uuid.uuid4().hex
    rng = random.Random(session_id)
    settings = await planning.settings_for_user(session, user.id)

    node, plan = await _plan_under_stable_scope(
        session, user=user, node_id=node_id, now=moment, settings=settings, rng=rng
    )

    meta = await session_store.create(
        redis,
        session_id,
        owner_id=user.id,
        node_id=node_id,
        scope_generation=node.structural_generation,
        target_words=settings.target_words_per_session,
        max_per_round=settings.max_questions_per_round,
        admitted=plan.admitted,
    )

    if plan.demands:
        # Round 0: the session exists but no round has been entered yet, and
        # `next_question` advances 0 -> 1 on the first call. Keying the warm-up at 0
        # means the first `/next` requests supply for round 1 under its own key
        # rather than joining this one, which is correct — they are different
        # demands, computed before and after admission.
        await request_supply(
            session,
            redis,
            session_id=session_id,
            owner_id=user.id,
            round_index=0,
            demands=[
                (int(d.sense_id), d.difficulty_level, d.expected_count)
                for d in plan.demands
            ],
        )

    return StartedSession(
        session_id=session_id,
        node_id=node_id,
        admitted_count=len(plan.admitted),
        expires_at=meta.expires_at,
        has_work=bool(plan.admitted),
    )


async def _plan_under_stable_scope(
    session: AsyncSession,
    *,
    user: CurrentUser,
    node_id: UUID,
    now: datetime,
    settings: planning.SessionSettings,
    rng: random.Random,
) -> tuple[Node, planning.PlanResult]:
    """Plan against a scope that did not change while the plan was being built.

    A structural mutation can move senses in or out of the subtree mid-request, so
    the generation is read before and after and the plan is discarded if it moved.

    Returning the successful attempt makes the scope invariant explicit.
    """
    for _ in range(_PLAN_ATTEMPTS):
        node = await require_node_access(session, node_id, user, write=False)
        generation = node.structural_generation
        plan = await planning.plan_session(session, user.id, node_id, now, settings, rng)
        node = await require_node_access(session, node_id, user, write=False)
        if node.structural_generation == generation:
            return node, plan
    raise ConflictError("session_scope_changed")


@dataclass(frozen=True)
class SupplyRequest:
    """What a supply request produced: its disposition, and a task to watch.

    ``task_id`` is set only for ``requested``, and is what makes the client's wait
    an event rather than a poll. The other three states start no work — there is
    nothing to announce, so there is nothing to subscribe to.
    """

    state: Literal["requested", "cooling", "no_slot", "exhausted"]
    task_id: UUID | None = None


async def request_supply(
    session: AsyncSession,
    redis: Redis,
    *,
    session_id: str,
    owner_id: UUID,
    round_index: int,
    demands: list[tuple[int, int, int]],
) -> SupplyRequest:
    """Ask the worker to generate questions, under a per-learner slot and a budget.

    Two independent bounds, both load-bearing and both easy to mistake for each
    other:

    - the generation slot is per learner over a short window, and caps how much
      costly generation one account can schedule;
    - the prepare attempt is per session, and is the only producer of
      ``question_preparation_exhausted`` — it caps how many supply jobs a single
      session can ever enqueue.

    The work is submitted through the task registry rather than enqueued directly,
    which is what gives the client something to subscribe to: the channel the
    subscribe proxy admits is ``async:{task_id}`` backed by a live interest, so
    without a task row there is no channel and the only way to learn that supply
    landed is to call ``/next`` again. That call mutates — it advances rounds and
    reserves deliveries — which is why asking repeatedly is the thing worth
    removing.

    The enqueue stays best-effort, and for a sharper reason than before: the task
    row is committed, so `reconcile_async_tasks` re-enqueues anything whose ARQ
    submission was lost. A failure here costs latency, not the work.
    """
    work_key = supply_work_key(session_id, round_index)

    # An already-running task for this round is reported before the bounds are
    # consulted. Both bounds guard *starting* generation, and neither has anything
    # to say about work already paid for — but reaching them first would answer
    # `cooling` with no task id, and the client reads a null id as "nothing to
    # subscribe to" and falls back to asking again. That is the exact case a reload
    # produces: the wait is re-established, the task is mid-flight, and the learner
    # would poll until the budget stalls while their questions were being written.
    live = await task_service.find_live_task(
        session, kind=TASK_KIND_QUESTION_SUPPLY, work_key=work_key
    )
    if live is not None:
        return SupplyRequest("requested", live.id)

    if not await session_store.take_generation_slot(redis, owner_id):
        return SupplyRequest("no_slot")
    state = await session_store.claim_prepare_attempt(redis, session_id)
    if state == "waiting":
        return SupplyRequest("cooling")
    if state != "claimed":
        return SupplyRequest("exhausted")

    dispatch = SupplyDispatch(
        owner_id=str(owner_id),
        session_id=session_id,
        round_index=round_index,
        demands=demands,
    )
    submission = await submit_and_dispatch(
        session,
        kind=TASK_KIND_QUESTION_SUPPLY,
        server_work_key=work_key,
        requester_id=owner_id,
        command_kind="question_supply.request",
        # One command per session-round, so a retried request joins the task it
        # already started instead of receipting a second one.
        command_id=f"{session_id}:{round_index}",
        provenance="session-owner",
        dispatch=dispatch,
    )
    return SupplyRequest("requested", submission.task.id)


async def authorize(
    session: AsyncSession, redis: Redis, session_id: str, user: CurrentUser
) -> session_store.SessionMeta:
    """The guard every session route shares: exists, is yours, and still in scope.

    A session belonging to someone else answers 404 exactly like an unknown id, so
    the endpoint never confirms that another learner's session exists.
    """
    meta = await session_store.get_meta(redis, session_id)
    if meta is None or meta.owner_id != user.id:
        raise NotFoundError("session_not_found")
    node = await require_node_access(session, meta.node_id, user, write=False)
    if node.structural_generation != meta.scope_generation:
        raise ConflictError("session_scope_changed")
    return meta


async def next_question(
    session: AsyncSession,
    redis: Redis,
    client: LexiReader,
    *,
    session_id: str,
    user: CurrentUser,
    meta: session_store.SessionMeta,
) -> DeliveryOutcome:
    """Advance the session by at most one delivery.

    This mutates: it advances rounds, reserves deliveries and extends the exclusion
    set. ``GET`` is the wrong verb for it and the plan has that on its own list; the
    behaviour is unchanged here so the extraction stays reviewable.
    """
    cur = await session_store.current_round(redis, session_id)
    # Round full -> offer a break; the next poll advances into a fresh round.
    if cur >= 1 and meta.round_count >= meta.max_per_round:
        await session_store.advance_round(redis, session_id, expected_round=cur)
        return RoundBreak(round_index=cur + 1)
    if cur == 0:
        cur = await session_store.advance_round(redis, session_id, expected_round=0)

    candidates = await round_scheduler.round_candidates(redis, session_id, cur)
    unresolved: list[tuple[int, int, int]] = []
    rng = random.Random(f"{session_id}:{cur}")

    for requirement in candidates:
        outcome = await _try_deliver(
            redis,
            client,
            session_id=session_id,
            requirement=requirement,
            round_index=cur,
            rng=rng,
            unresolved=unresolved,
        )
        if outcome is not None:
            return outcome

    # Nothing delivered this round.
    if unresolved:
        supply = await request_supply(
            session,
            redis,
            session_id=session_id,
            owner_id=user.id,
            round_index=cur,
            demands=unresolved,
        )
        if supply.state == "exhausted":
            raise ServiceUnavailableError("question_preparation_exhausted")
        return NoQuestionYet(reason="preparing", supply_task_id=supply.task_id)
    if candidates:
        # A concurrent request reserved the eligible candidate first.
        return NoQuestionYet(reason="preparing")
    if await round_scheduler.has_open_work(redis, session_id):
        # Remaining work waits for a later round (retries / used-this-round).
        await session_store.advance_round(redis, session_id, expected_round=cur)
        return RoundBreak(round_index=cur + 1)
    if await round_scheduler.session_complete(session, redis, session_id):
        # The recap must be written while the Redis state still exists — end_session
        # deletes the namespace on the next line.
        await session_recap.persist(
            session, redis, session_id, user_id=user.id, node_id=meta.node_id
        )
        await session_store.end_session(redis, session_id)
        return NoQuestionYet(reason="exhausted")
    return NoQuestionYet(reason="waiting")


async def _try_deliver(
    redis: Redis,
    client: LexiReader,
    *,
    session_id: str,
    requirement,
    round_index: int,
    rng: random.Random,
    unresolved: list[tuple[int, int, int]],
) -> DeliveryOutcome | None:
    """Serve one candidate, or return None to try the next.

    Deferring rather than failing is the rule throughout: a missing sense, cold
    supply, a non-integer question id and a lost reservation race all mean "try
    someone else", never a 500.
    """
    sense_id = requirement.sense_id

    if requirement.kind == "exposure":
        try:
            resolved = await resolver.resolve_exposure(client, sense_id)
        except LookupError:
            return None  # Missing or stale sense: defer instead of failing the request.
        if not await session_store.reserve_round_delivery(
            redis, session_id, sense_id, round_index, question_id=None
        ):
            return None
        return Delivered(resolved=resolved)

    excluded = await session_store.excluded_ids(redis, session_id, sense_id)
    resolved = await resolver.resolve(
        client, sense_id, requirement.requested_level, excluded, rng
    )
    if resolved is None:
        unresolved.append((sense_id, requirement.requested_level, 1))
        return None  # defer: supply not warm -> try next candidate
    try:
        question_id = int(resolved.question.question_id)
    except (TypeError, ValueError):
        # Assessment ids must remain integer-compatible on the REST wire.
        return None
    if not await session_store.reserve_round_delivery(
        redis, session_id, sense_id, round_index, question_id=question_id
    ):
        return None
    return Delivered(resolved=resolved)


@dataclass(frozen=True)
class SenseProgressView:
    sense_id: int
    purpose: str
    passed: int
    required: int
    score: float | None
    exposed: bool
    awaiting_grade: bool
    terminal: bool
    terminal_reason: str | None


@dataclass(frozen=True)
class LiveSessionView:
    """A read-only snapshot of a live session. Mutates nothing."""

    meta: session_store.SessionMeta
    senses: list[SenseProgressView]
    senses_admitted: int
    senses_completed: int
    senses_exhausted: int
    answers_total: int
    answers_correct: int


async def read_live(
    session: AsyncSession, redis: Redis, session_id: str, *, user_id: UUID
) -> LiveSessionView | None:
    """Snapshot a live session, or None when its Redis namespace is gone.

    A TRUE read: it advances nothing and reserves nothing, so it is safe to poll,
    retry and prefetch — the counter-example to ``next_question`` above.

    Returns None both for an unknown session and for someone else's, so the caller
    answers the same 404 either way and never confirms that another learner's session
    exists.
    """
    meta = await session_store.get_meta(redis, session_id)
    if meta is None or meta.owner_id != user_id:
        return None

    admitted = await session_store.get_admitted(redis, session_id)
    senses: list[SenseProgressView] = []
    completed = 0
    exhausted = 0
    for sense_id, purpose in sorted(admitted.items()):
        progress = await session_store.get_progress(redis, session_id, sense_id)
        if progress is None:
            # A progress key can expire independently of the session hash; such a
            # sense has neither completed nor been exhausted.
            continue
        if progress.terminal_reason == "retries_exhausted":
            exhausted += 1
        elif progress.terminal:
            # Checked after `retries_exhausted` on purpose: that state is terminal
            # too, so testing `terminal` first would report a failure as a success.
            completed += 1
        senses.append(
            SenseProgressView(
                sense_id=sense_id,
                purpose=purpose,
                passed=progress.passed,
                required=len(progress.requested_levels),
                score=progress.score,
                exposed=progress.exposed,
                awaiting_grade=progress.awaiting_grade,
                terminal=progress.terminal,
                terminal_reason=progress.terminal_reason,
            )
        )

    answers_total, answers_correct = await session_recap.answer_counts(
        session, user_id, session_id
    )
    return LiveSessionView(
        meta=meta,
        senses=senses,
        senses_admitted=len(admitted),
        senses_completed=completed,
        senses_exhausted=exhausted,
        answers_total=answers_total,
        answers_correct=answers_correct,
    )
