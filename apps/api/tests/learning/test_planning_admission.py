"""The admission algorithm, tested directly rather than through the route.

`planning.py` decides what a session *is*: which senses enter it, how many
checkpoints each one owes, at which requested level, and what supply must be
generated to serve them. Until now every one of those decisions was observed only
through `POST /v1/sessions`, which reports `admitted_count` and nothing else — so
the split between new and due words, the floor that protects new words under a
backlog, the backfill that stops a session being short, and the demand aggregation
that drives paid LLM generation were all invisible to the suite.

The seams are `_slot_split` (how many of each kind may enter), `_admit` (who
actually enters, plus backfill), `_requirements` (what each admitted sense owes),
and `_demands` (what supply that implies). They are pure functions of their
arguments, so they are tested as such; `plan_session` is then tested against a real
database to prove the composition matches.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from sqlalchemy import update

from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ConflictError
from pycil.content.application import service as content_service
from pycil.db.redis import get_redis
from pycil.hierarchy.application import service as hierarchy_service
from pycil.hierarchy.infra.models import NodeType
from pycil.hierarchy.infra.models import Node
from pycil.learning.application import planning, session_flow, session_queue
from pycil.learning.infra.models import SenseStatus, UserSenseStats
from pycil.policy.policy import (
    ASSESSMENT_FLOOR,
    NEW_WORD_FLOOR,
    REQUIRED_CHECKPOINTS,
)

# No module-level `asyncio` mark: this file mixes pure-function tests with
# database-backed ones, and `asyncio_mode = "auto"` already collects the async ones.
# Marking the sync tests too made pytest warn on every one of them.


def _due(sense_id: int, mastery: int = 50) -> session_queue.DueCandidate:
    return session_queue.DueCandidate(
        sense_id=sense_id, mastery=mastery, recall=0.5, overdue_seconds=0.0
    )


# --- _slot_split: the new-word floor ------------------------------------------


def test_the_floor_reserves_new_words_under_a_large_backlog():
    """The whole point of `NEW_WORD_FLOOR`: a backlog must not stop acquisition.

    With 500 due words and a 10-word session, a plain due-first split would fill
    every slot with reviews and the learner would never see a new word again. The
    floor is what makes progress possible on a deck you have fallen behind on.
    """
    new_slots, due_slots = planning._slot_split(target=10, due_available=500)

    assert new_slots == NEW_WORD_FLOOR
    assert due_slots == 10 - NEW_WORD_FLOOR


def test_no_backlog_gives_every_slot_to_new_words():
    new_slots, due_slots = planning._slot_split(target=10, due_available=0)

    assert (new_slots, due_slots) == (10, 0)


@pytest.mark.parametrize("target", [1, 2, 3, 4, 5, 10, 37, 100])
@pytest.mark.parametrize("due_available", [0, 1, 2, 5, 500])
def test_the_split_always_sums_to_target_and_never_goes_negative(target, due_available):
    """`due_slots` is `target - new_slots`, so an unclamped floor would go negative.

    At `target=1` the floor of 2 exceeds the whole session; without the `min(...,
    target)` clamp this returns `due_slots == -1`, and `due[:−1]` silently drops the
    last due candidate instead of taking none — a slice bug rather than an error.
    """
    new_slots, due_slots = planning._slot_split(target, due_available)

    assert new_slots >= 0
    assert due_slots >= 0
    assert new_slots + due_slots == target
    assert new_slots <= target


def test_a_session_smaller_than_the_floor_is_all_new_words():
    """Documents the deliberate consequence of clamping rather than erroring."""
    assert planning._slot_split(target=1, due_available=500) == (1, 0)
    assert planning._slot_split(target=2, due_available=500) == (2, 0)


# --- _admit: backfill --------------------------------------------------------


def test_a_shortfall_of_new_words_is_backfilled_with_due_words():
    """Slots are a target, not a quota. An empty deck of new words must not shrink
    the session when there are reviews waiting to use those slots."""
    due = [_due(i) for i in range(100, 120)]
    new_slots, due_slots = planning._slot_split(target=10, due_available=len(due))

    admitted_due, admitted_new = planning._admit(due, [], 10, new_slots, due_slots)

    assert admitted_new == []
    assert len(admitted_due) == 10


def test_a_shortfall_of_due_words_is_backfilled_with_new_words():
    new = list(range(1, 21))

    new_slots, due_slots = planning._slot_split(target=10, due_available=0)
    admitted_due, admitted_new = planning._admit([], new, 10, new_slots, due_slots)

    assert admitted_due == []
    assert len(admitted_new) == 10


def test_backfill_prefers_due_words():
    """When both kinds have surplus, the spare capacity goes to reviews first.

    Reviews are time-sensitive — a due word decays — whereas a new word can wait for
    the next session at no cost. Only reachable when the floor is *larger* than the
    new words actually available, so the freed slots are redistributed.
    """
    due = [_due(i) for i in range(100, 120)]
    new = [1]  # one new word, but the floor reserves two slots

    new_slots, due_slots = planning._slot_split(target=10, due_available=len(due))
    admitted_due, admitted_new = planning._admit(due, new, 10, new_slots, due_slots)

    assert admitted_new == [1]
    # The unused new slot went to a review rather than being wasted.
    assert len(admitted_due) == 9
    assert len(admitted_due) + len(admitted_new) == 10


def test_admission_never_exceeds_the_target():
    """The session length the learner configured is a hard cap, and the backfill is
    the code most likely to break it."""
    due = [_due(i) for i in range(100, 200)]
    new = list(range(1, 100))

    for target in (1, 2, 3, 5, 10, 50):
        new_slots, due_slots = planning._slot_split(target, len(due))
        admitted_due, admitted_new = planning._admit(due, new, target, new_slots, due_slots)
        assert len(admitted_due) + len(admitted_new) == target


def test_a_thin_deck_yields_a_short_session_rather_than_an_error():
    """Fewer candidates than slots is the normal state of a new deck."""
    due = [_due(100)]
    new = [1]

    new_slots, due_slots = planning._slot_split(target=10, due_available=1)
    admitted_due, admitted_new = planning._admit(due, new, 10, new_slots, due_slots)

    assert len(admitted_due) + len(admitted_new) == 2


def test_admission_takes_due_candidates_in_the_order_given():
    """`session_queue` ranks weakest-recall-first; admission must not reorder it,
    or the ranking work is discarded."""
    due = [_due(sense_id) for sense_id in (105, 101, 103)]

    admitted_due, _ = planning._admit(due, [], target=2, new_slots=0, due_slots=2)

    assert [c.sense_id for c in admitted_due] == [105, 101]


# --- _requirements -----------------------------------------------------------


def test_a_new_word_always_requests_the_assessment_floor():
    """Acquisition never samples difficulty: a word being seen for the first time is
    checked at the floor, so `sample_requested_level` must not touch it."""
    admitted = planning._requirements([], [1, 2], random.Random(0))

    assert [item.purpose for item in admitted] == ["new", "new"]
    for item in admitted:
        assert item.requested_levels == [ASSESSMENT_FLOOR] * REQUIRED_CHECKPOINTS


def test_each_checkpoint_of_a_due_word_samples_its_level_independently():
    """Levels are sampled per checkpoint at PLAN time, not once per sense.

    Sampling once and reusing it would make both checkpoints identical; sampling at
    delivery time would let a retry land on a different level than the checkpoint was
    created with. Fixing them here is what makes a retry preserve its own level.
    """
    # Mid-band mastery, where the profile spans several levels, so a per-sense sample
    # would be visible as a constant.
    due = [_due(sense_id, mastery=45) for sense_id in range(100, 140)]

    admitted = planning._requirements(due, [], random.Random(7))

    assert all(len(item.requested_levels) == REQUIRED_CHECKPOINTS for item in admitted)
    varied = [item for item in admitted if len(set(item.requested_levels)) > 1]
    assert varied, "every sense drew the same level for both checkpoints"


def test_requested_levels_are_reproducible_for_a_seeded_rng():
    """The session id seeds the RNG in the route, so the same session replans
    identically — that is what makes a plan explainable after the fact."""
    due = [_due(i, mastery=45) for i in range(100, 110)]

    first = planning._requirements(due, [], random.Random(11))
    second = planning._requirements(due, [], random.Random(11))

    assert [i.requested_levels for i in first] == [i.requested_levels for i in second]


def test_mastery_moves_the_sampled_levels_upward():
    """A learner who knows a word well should be asked harder questions about it.

    Asserted as an aggregate over many senses rather than per sample: the profile is
    a distribution, so a single draw proves nothing.
    """
    beginner = planning._requirements(
        [_due(i, mastery=5) for i in range(100, 200)], [], random.Random(3)
    )
    fluent = planning._requirements(
        [_due(i, mastery=95) for i in range(100, 200)], [], random.Random(3)
    )

    def mean(items):
        levels = [lvl for item in items for lvl in item.requested_levels]
        return sum(levels) / len(levels)

    assert mean(beginner) < mean(fluent)


def test_due_senses_come_before_new_ones():
    """Purpose ordering is load-bearing: `session_store.create` stores this list and
    the round scheduler walks it, so reviews are offered before acquisitions."""
    admitted = planning._requirements([_due(100)], [1], random.Random(0))

    assert [item.purpose for item in admitted] == ["due", "new"]


# --- _demands ----------------------------------------------------------------


def test_demand_is_aggregated_per_sense_and_level():
    """Two checkpoints at the same level are one demand for two questions, not two
    demands for one. This number is what the worker generates, and generation costs
    money — over-counting buys supply nobody asked for."""
    admitted = planning._requirements([], [1, 2], random.Random(0))

    demands = planning._demands(admitted)

    assert {(d.sense_id, d.difficulty_level, d.expected_count) for d in demands} == {
        ("1", ASSESSMENT_FLOOR, REQUIRED_CHECKPOINTS),
        ("2", ASSESSMENT_FLOOR, REQUIRED_CHECKPOINTS),
    }


def test_demand_counts_match_the_checkpoints_that_were_planned():
    """The invariant that ties the two halves together: total demanded questions
    equals total planned checkpoints, whatever the level mix."""
    due = [_due(i, mastery=45) for i in range(100, 130)]
    admitted = planning._requirements(due, [1, 2, 3], random.Random(5))

    demands = planning._demands(admitted)

    planned = sum(len(item.requested_levels) for item in admitted)
    assert sum(d.expected_count for d in demands) == planned


def test_demand_sense_ids_are_strings_on_the_lexi_contract():
    """`PrepareDemand.sense_id` crosses into Lexi as a string; an int would be a
    silent contract break at the boundary."""
    admitted = planning._requirements([_due(100)], [], random.Random(0))

    for demand in planning._demands(admitted):
        assert isinstance(demand.sense_id, str)


def test_an_empty_plan_demands_nothing():
    """A session with nothing admitted must not enqueue a generation job — that is
    the difference between a quiet no-op and a paid LLM call for no reason."""
    assert planning._demands([]) == []


# --- plan_session: the composition, against a real database ------------------


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _deck(session, author_id, sense_ids: list[int]):
    deck = await hierarchy_service.create_node(
        session, author_id, node_type=NodeType.DECK, name="deck"
    )
    for sense_id in sense_ids:
        await content_service.add_sense(session, deck.id, sense_id)
    return deck


async def test_plan_session_reserves_new_words_against_a_real_backlog(session):
    """End to end through the database: 30 scheduled-and-overdue senses plus 5 fresh
    ones, and the floor still gets the new words in."""
    owner = await _user(session, "planning-floor@example.com")
    due_ids = list(range(100, 130))
    new_ids = list(range(200, 205))
    deck = await _deck(session, owner.id, due_ids + new_ids)

    now = datetime.now(UTC)
    for sense_id in due_ids:
        session.add(
            UserSenseStats(
                user_id=owner.id,
                sense_id=sense_id,
                status=SenseStatus.scheduled,
                mastery=40,
                stability=3.0,
                review_count=2,
                last_review_date=now - timedelta(days=5),
                next_review_date=now - timedelta(days=1),
            )
        )
    await session.commit()

    plan = await planning.plan_session(
        session,
        owner.id,
        deck.id,
        now,
        planning.SessionSettings(target_words_per_session=10, max_questions_per_round=8),
        random.Random(1),
    )

    assert len(plan.admitted) == 10
    purposes = [item.purpose for item in plan.admitted]
    assert purposes.count("new") == NEW_WORD_FLOOR
    assert purposes.count("due") == 10 - NEW_WORD_FLOOR
    # Every admitted sense is in scope, and none appears twice.
    admitted_ids = [item.sense_id for item in plan.admitted]
    assert len(set(admitted_ids)) == len(admitted_ids)
    assert set(admitted_ids) <= set(due_ids + new_ids)


async def test_plan_session_admits_the_weakest_due_senses_first(session):
    """The ranking `session_queue` computes has to survive into the plan."""
    owner = await _user(session, "planning-weakest@example.com")
    sense_ids = list(range(300, 310))
    deck = await _deck(session, owner.id, sense_ids)

    now = datetime.now(UTC)
    # Same due time, deliberately different stability: recall is what ranks them, and
    # low stability after the same elapsed time means lower recall.
    for offset, sense_id in enumerate(sense_ids):
        session.add(
            UserSenseStats(
                user_id=owner.id,
                sense_id=sense_id,
                status=SenseStatus.scheduled,
                mastery=40,
                stability=1.0 + offset * 10.0,
                review_count=2,
                last_review_date=now - timedelta(days=5),
                next_review_date=now - timedelta(days=1),
            )
        )
    await session.commit()

    plan = await planning.plan_session(
        session,
        owner.id,
        deck.id,
        now,
        planning.SessionSettings(target_words_per_session=4, max_questions_per_round=8),
        random.Random(1),
    )

    due_admitted = [i.sense_id for i in plan.admitted if i.purpose == "due"]
    # The two lowest-stability senses are the weakest, so they must be present.
    assert 300 in due_admitted
    assert 301 in due_admitted


async def test_plan_session_excludes_a_buried_sense(session):
    """Burying is the learner saying "not this one"; the planner must honour it even
    though the sense is otherwise a perfect candidate."""
    owner = await _user(session, "planning-buried@example.com")
    deck = await _deck(session, owner.id, [400, 401])

    now = datetime.now(UTC)
    session.add(
        UserSenseStats(
            user_id=owner.id,
            sense_id=400,
            status=SenseStatus.new,
            buried_until=now + timedelta(days=3),
        )
    )
    await session.commit()

    plan = await planning.plan_session(
        session,
        owner.id,
        deck.id,
        now,
        planning.SessionSettings(target_words_per_session=10, max_questions_per_round=8),
        random.Random(1),
    )

    assert [item.sense_id for item in plan.admitted] == [401]


async def test_plan_session_excludes_a_scheduled_sense_that_is_not_due(session):
    """FSRS's whole value is not asking early. A sense scheduled for next week must
    not be pulled into today's session."""
    owner = await _user(session, "planning-not-due@example.com")
    deck = await _deck(session, owner.id, [500])

    now = datetime.now(UTC)
    session.add(
        UserSenseStats(
            user_id=owner.id,
            sense_id=500,
            status=SenseStatus.scheduled,
            mastery=60,
            stability=10.0,
            review_count=3,
            last_review_date=now - timedelta(days=1),
            next_review_date=now + timedelta(days=7),
        )
    )
    await session.commit()

    plan = await planning.plan_session(
        session,
        owner.id,
        deck.id,
        now,
        planning.SessionSettings(target_words_per_session=10, max_questions_per_round=8),
        random.Random(1),
    )

    assert plan.admitted == []
    assert plan.demands == []


async def test_plan_session_on_an_empty_deck_plans_nothing(session):
    owner = await _user(session, "planning-empty@example.com")
    deck = await _deck(session, owner.id, [])

    plan = await planning.plan_session(
        session,
        owner.id,
        deck.id,
        datetime.now(UTC),
        planning.SessionSettings(target_words_per_session=10, max_questions_per_round=8),
        random.Random(1),
    )

    assert plan.admitted == []
    assert plan.demands == []


async def test_plan_session_is_deterministic_for_the_same_seed(session):
    """The route seeds the RNG from the session id, so replanning the same session
    must produce the same requested levels."""
    owner = await _user(session, "planning-seed@example.com")
    sense_ids = list(range(600, 620))
    deck = await _deck(session, owner.id, sense_ids)

    now = datetime.now(UTC)
    for sense_id in sense_ids:
        session.add(
            UserSenseStats(
                user_id=owner.id,
                sense_id=sense_id,
                status=SenseStatus.scheduled,
                mastery=45,
                stability=3.0,
                review_count=2,
                last_review_date=now - timedelta(days=5),
                next_review_date=now - timedelta(days=1),
            )
        )
    await session.commit()

    settings = planning.SessionSettings(
        target_words_per_session=8, max_questions_per_round=8
    )
    seed = uuid.uuid4().hex
    first = await planning.plan_session(
        session, owner.id, deck.id, now, settings, random.Random(seed)
    )
    second = await planning.plan_session(
        session, owner.id, deck.id, now, settings, random.Random(seed)
    )

    assert [(i.sense_id, i.purpose, i.requested_levels) for i in first.admitted] == [
        (i.sense_id, i.purpose, i.requested_levels) for i in second.admitted
    ]


async def test_plan_session_does_not_see_another_learners_progress(session):
    """Stats are per learner. Reading someone else's would make a word that *they*
    have scheduled disappear from *your* new-word pool."""
    mine = await _user(session, "planning-mine@example.com")
    theirs = await _user(session, "planning-theirs@example.com")
    deck = await _deck(session, mine.id, [700])

    now = datetime.now(UTC)
    session.add(
        UserSenseStats(
            user_id=theirs.id,
            sense_id=700,
            status=SenseStatus.scheduled,
            mastery=90,
            stability=50.0,
            review_count=9,
            last_review_date=now - timedelta(days=1),
            next_review_date=now + timedelta(days=30),
        )
    )
    await session.commit()

    plan = await planning.plan_session(
        session,
        mine.id,
        deck.id,
        now,
        planning.SessionSettings(target_words_per_session=10, max_questions_per_round=8),
        random.Random(1),
    )

    # Still a new word to me, despite being long-scheduled for them.
    assert [(i.sense_id, i.purpose) for i in plan.admitted] == [(700, "new")]


async def test_session_start_gives_up_when_the_scope_keeps_moving(session, monkeypatch):
    """The bound on re-planning, which nothing else reaches.

    A structural mutation can move senses in or out of the subtree while a plan is
    being built, so the generation is read before and after and the plan discarded
    if it moved. That retry needs a ceiling: without one, a node under sustained
    mutation re-plans forever, holding a request open and paying for the planning
    query each pass.

    Unreachable by any ordinary test, which is why it went unasserted — the
    generation only moves if something mutates the node mid-plan, and no test does.
    So planning is made to bump it on every call, which is the pathological case
    stated directly.
    """
    owner = await _user(session, "scope-churn@example.com")
    deck = await _deck(session, owner.id, [4101, 4102])

    calls = 0
    real_plan_session = planning.plan_session

    async def churning_plan(db, *args, **kwargs):
        # Mutating the scope from inside the plan is exactly the interleaving the
        # generation check exists to catch: the "after" read can never match.
        nonlocal calls
        calls += 1
        result = await real_plan_session(db, *args, **kwargs)
        await db.execute(
            update(Node)
            .where(Node.id == deck.id)
            .values(structural_generation=Node.structural_generation + 1)
        )
        await db.commit()
        return result

    monkeypatch.setattr(session_flow.planning, "plan_session", churning_plan)

    with pytest.raises(ConflictError) as raised:
        await session_flow.start(
            session,
            get_redis(),
            user=CurrentUser(id=owner.id, email=owner.email),
            node_id=deck.id,
        )

    assert raised.value.code == "session_scope_changed"
    # Bounded, and bounded at the stated number: a loop that gave up after one
    # attempt would never tolerate the single concurrent mutation this exists to
    # absorb, and one that never gave up would not reach this assertion at all.
    assert calls == session_flow._PLAN_ATTEMPTS, (
        f"planning ran {calls} times against a ceiling of "
        f"{session_flow._PLAN_ATTEMPTS}"
    )
