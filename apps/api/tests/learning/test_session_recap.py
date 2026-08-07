"""The recap is written once and then corrected — so the upsert must actually update.

`session_recap.persist` is called just before `end_session` deletes the Redis
namespace, and both `/next` and `/answers` can reach the completion predicate for
the same session. The insert is therefore `ON CONFLICT ... DO UPDATE`.

The existing idempotency test only asserted that calling `persist` twice does not
raise. That is satisfied by `DO NOTHING` too: swapping the clause leaves the whole
suite green while silently discarding the second write. So these tests assert the
*values* change, not merely that the call survives.

That distinction is the bug this file guards. The first caller can win the race
before the last grade lands, and its snapshot is then the one the learner sees
forever: fewer answers than they gave, and a session that looks unfinished.
"""

from __future__ import annotations

import uuid

import fakeredis.aioredis as fake_aioredis

from pycil.auth.models import User
from pycil.hierarchy.application import service as hierarchy_service
from pycil.hierarchy.infra.models import NodeType
from pycil.learning.application import session_recap
from pycil.learning.infra import session_store
from pycil.learning.infra.models import Response
from pycil.learning.infra.session_store import AdmittedSense
from tests.learning import session_state


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _deck(session, author_id):
    return await hierarchy_service.create_node(
        session, author_id, node_type=NodeType.DECK, name="deck"
    )


async def _live(session, owner, *, admitted=None):
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    deck = await _deck(session, owner.id)
    sid = uuid.uuid4().hex
    await session_store.create(
        redis,
        sid,
        owner_id=owner.id,
        node_id=deck.id,
        scope_generation=1,
        target_words=3,
        max_per_round=4,
        admitted=admitted
        or [AdmittedSense(10, "due", [2, 2]), AdmittedSense(20, "new", [1, 1])],
    )
    return redis, sid, deck


async def _answer(session, owner, sid, sense_id, question_id, *, correct):
    session.add(
        Response(
            user_id=owner.id,
            session_id=sid,
            sense_id=sense_id,
            question_id=question_id,
            is_correct=correct,
        )
    )
    await session.commit()


# --- the upsert has to be an update -----------------------------------------


async def test_a_later_persist_corrects_the_counts_of_an_earlier_one(session):
    """The race that makes this load-bearing.

    `/next` can persist the recap while a grade is still settling, and `/answers`
    persists again once it lands. With `DO NOTHING` the first, incomplete snapshot is
    frozen: the learner's recap under-reports the answers they actually gave.
    """
    owner = await _user(session, "recap-correct@example.com")
    redis, sid, deck = await _live(session, owner)

    await _answer(session, owner, sid, 10, 1, correct=True)
    await session_recap.persist(session, redis, sid, user_id=owner.id, node_id=deck.id)

    early = await session_recap.load(session, owner.id, sid)
    assert (early.answers_total, early.answers_correct) == (1, 1)

    # The pending grade settles after the first persist.
    await _answer(session, owner, sid, 20, 2, correct=True)
    await session_recap.persist(session, redis, sid, user_id=owner.id, node_id=deck.id)

    corrected = await session_recap.load(session, owner.id, sid)
    await session.refresh(corrected)
    assert (corrected.answers_total, corrected.answers_correct) == (2, 2)


async def test_a_later_persist_corrects_the_completion_counts(session):
    """Same trap on the counts the recap screen actually renders as progress."""
    owner = await _user(session, "recap-progress@example.com")
    redis, sid, deck = await _live(session, owner)

    await session_recap.persist(session, redis, sid, user_id=owner.id, node_id=deck.id)
    first = await session_recap.load(session, owner.id, sid)
    assert first.senses_completed == 0

    await session_state.pass_checkpoint(redis, sid, 10, required_checkpoints=2)
    await session_state.pass_checkpoint(redis, sid, 10, required_checkpoints=2)
    await session_recap.persist(session, redis, sid, user_id=owner.id, node_id=deck.id)

    second = await session_recap.load(session, owner.id, sid)
    await session.refresh(second)
    assert second.senses_completed == 1


async def test_a_later_persist_corrects_rounds_used(session):
    owner = await _user(session, "recap-rounds@example.com")
    redis, sid, deck = await _live(session, owner)

    await session_recap.persist(session, redis, sid, user_id=owner.id, node_id=deck.id)
    assert (await session_recap.load(session, owner.id, sid)).rounds_used == 1

    await session_store.advance_round(redis, sid, expected_round=0)
    await session_store.advance_round(redis, sid, expected_round=1)
    await session_recap.persist(session, redis, sid, user_id=owner.id, node_id=deck.id)

    reloaded = await session_recap.load(session, owner.id, sid)
    await session.refresh(reloaded)
    assert reloaded.rounds_used == 3


async def test_persisting_repeatedly_never_duplicates_the_row(session):
    """The other half of the constraint: one recap per (learner, session)."""
    owner = await _user(session, "recap-single-row@example.com")
    redis, sid, deck = await _live(session, owner)

    for _ in range(4):
        await session_recap.persist(
            session, redis, sid, user_id=owner.id, node_id=deck.id
        )

    from sqlalchemy import func, select

    from pycil.learning.infra.models import SessionSummary

    count = (
        await session.execute(
            select(func.count()).where(
                SessionSummary.user_id == owner.id, SessionSummary.session_id == sid
            )
        )
    ).scalar()
    assert count == 1


# --- what the counts mean ----------------------------------------------------


async def test_an_exhausted_sense_is_not_counted_as_completed(session):
    """`retries_exhausted` and `terminal` are different outcomes for the learner.

    A sense that ran out of retries is terminal too, so an `if terminal` written
    before the `retries_exhausted` branch would report a failure as a success. This is
    the `elif` in `persist` — previously uncovered.
    """
    owner = await _user(session, "recap-exhausted@example.com")
    redis, sid, deck = await _live(session, owner)

    await session_state.pass_checkpoint(redis, sid, 10, required_checkpoints=2)
    await session_state.pass_checkpoint(redis, sid, 10, required_checkpoints=2)
    await session_state.open_retry(
        redis, sid, 20, requested_level=1, retries_used=3, failed_round=1, max_retries=2
    )

    await session_recap.persist(session, redis, sid, user_id=owner.id, node_id=deck.id)

    recap = await session_recap.load(session, owner.id, sid)
    assert recap.senses_admitted == 2
    assert recap.senses_completed == 1
    assert recap.senses_exhausted == 1


async def test_an_admitted_sense_with_no_progress_row_is_skipped(session):
    """The `continue` in `persist`, previously uncovered.

    A progress key can expire independently of the session hash, and an admitted
    sense with no progress has neither completed nor been exhausted — counting it as
    either would misreport the session.
    """
    owner = await _user(session, "recap-missing-progress@example.com")
    redis, sid, deck = await _live(session, owner)
    await session_state.pass_checkpoint(redis, sid, 10, required_checkpoints=2)
    await session_state.pass_checkpoint(redis, sid, 10, required_checkpoints=2)

    # Drop one admitted sense's progress key, leaving the admission list intact.
    # Keyed through the store's own helper rather than a literal, so a key-layout
    # change breaks the store's tests instead of silently making this one vacuous.
    deleted = await redis.delete(session_store._sense_key(sid, 20))
    assert deleted == 1

    await session_recap.persist(session, redis, sid, user_id=owner.id, node_id=deck.id)

    recap = await session_recap.load(session, owner.id, sid)
    assert recap.senses_admitted == 2
    assert recap.senses_completed == 1
    assert recap.senses_exhausted == 0


async def test_a_pending_grade_counts_as_answered_but_not_correct(session):
    """A grade in flight is answered but not yet correct.

    Note what this does *not* prove. The module's docstring used to claim the `CASE`
    "keeps NULL out of the sum instead of poisoning it"; measured against Postgres,
    `SUM` already ignores NULLs, so replacing the `CASE` with a bare
    `SUM(is_correct::int)` leaves all of these green. The clause that is actually
    load-bearing is the `COALESCE` — see the zero-answers test below, where removing
    it fails 8 tests. The docstring was corrected to say so.
    """
    owner = await _user(session, "recap-pending@example.com")
    redis, sid, deck = await _live(session, owner)

    await _answer(session, owner, sid, 10, 1, correct=True)
    await _answer(session, owner, sid, 20, 2, correct=None)

    await session_recap.persist(session, redis, sid, user_id=owner.id, node_id=deck.id)

    recap = await session_recap.load(session, owner.id, sid)
    assert (recap.answers_total, recap.answers_correct) == (2, 1)


async def test_counts_ignore_another_learners_answers_in_the_same_session_id(session):
    """Session ids are random hex, not scoped by user, so the query must filter on
    both. Without the user predicate one learner's answers would inflate another's
    recap."""
    owner = await _user(session, "recap-mine@example.com")
    stranger = await _user(session, "recap-theirs@example.com")
    redis, sid, deck = await _live(session, owner)

    await _answer(session, owner, sid, 10, 1, correct=True)
    await _answer(session, stranger, sid, 10, 2, correct=True)

    total, correct = await session_recap.answer_counts(session, owner.id, sid)

    assert (total, correct) == (1, 1)


async def test_counts_ignore_the_same_learners_other_sessions(session):
    owner = await _user(session, "recap-other-session@example.com")
    redis, sid, deck = await _live(session, owner)
    other_sid = uuid.uuid4().hex

    await _answer(session, owner, sid, 10, 1, correct=True)
    await _answer(session, owner, other_sid, 10, 2, correct=True)

    total, correct = await session_recap.answer_counts(session, owner.id, sid)

    assert (total, correct) == (1, 1)


async def test_a_session_with_no_answers_reports_zero_not_null(session):
    """`COALESCE` around the SUM: an empty set sums to NULL, and `int(None)` raises.
    A learner who starts a session and leaves must still get a recap."""
    owner = await _user(session, "recap-no-answers@example.com")
    redis, sid, deck = await _live(session, owner)

    total, correct = await session_recap.answer_counts(session, owner.id, sid)
    assert (total, correct) == (0, 0)

    await session_recap.persist(session, redis, sid, user_id=owner.id, node_id=deck.id)
    recap = await session_recap.load(session, owner.id, sid)
    assert (recap.answers_total, recap.answers_correct) == (0, 0)


async def test_persist_after_the_namespace_is_gone_records_zero_rounds(session):
    """Defensive path: `meta is None` must not crash the recap write.

    `persist` is documented as running before `end_session`, but a crash between the
    two would otherwise make the retry raise on `meta.round_index`.
    """
    owner = await _user(session, "recap-no-meta@example.com")
    redis, sid, deck = await _live(session, owner)
    await session_store.end_session(redis, sid)

    await session_recap.persist(session, redis, sid, user_id=owner.id, node_id=deck.id)

    recap = await session_recap.load(session, owner.id, sid)
    assert recap is not None
    assert recap.rounds_used == 0
    assert recap.senses_admitted == 0


async def test_load_is_scoped_to_the_owner(session):
    owner = await _user(session, "recap-load-owner@example.com")
    stranger = await _user(session, "recap-load-stranger@example.com")
    redis, sid, deck = await _live(session, owner)
    await session_recap.persist(session, redis, sid, user_id=owner.id, node_id=deck.id)

    assert await session_recap.load(session, owner.id, sid) is not None
    assert await session_recap.load(session, stranger.id, sid) is None


async def test_load_returns_none_for_a_session_that_never_completed(session):
    owner = await _user(session, "recap-load-missing@example.com")

    assert await session_recap.load(session, owner.id, uuid.uuid4().hex) is None
