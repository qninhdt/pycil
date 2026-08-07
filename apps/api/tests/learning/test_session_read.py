"""GET /v1/sessions/{id}: a true read that survives session completion.

Two things were missing. There was no session read endpoint at all, so a reload
mid-session had nothing to rehydrate from. And ``end_session`` deletes the entire
Redis namespace the moment a session completes, so even if one had existed it would
have 404'd exactly when the learner wanted their recap.

This endpoint is also the counter-example to ``/next``, which is a mutation dressed
as a GET — it advances rounds, reserves deliveries and extends the exclusion set.
This one must mutate nothing, so it is safe to poll, retry and prefetch.
"""

import uuid

import fakeredis.aioredis as fake_aioredis
import pytest

from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import NotFoundError
from pycil.db import redis as redis_module
from pycil.hierarchy.application import service as hierarchy_service
from pycil.hierarchy.infra.models import NodeType
from pycil.learning.application import session_recap
from pycil.learning.infra import session_store
from pycil.learning.infra.models import Response
from pycil.learning.infra.session_store import AdmittedSense
from pycil.learning.router import read_session
from tests.learning import session_state

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _cu(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, email=user.email)


async def _live_session(session, monkeypatch, owner, *, admitted=None):
    """Create a live session over a fake Redis wired into the app's accessor."""
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "_redis", redis)
    deck = await hierarchy_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="deck"
    )
    sid = uuid.uuid4().hex
    await session_store.create(
        redis,
        sid,
        owner_id=owner.id,
        node_id=deck.id,
        scope_generation=1,
        target_words=3,
        max_per_round=4,
        admitted=admitted or [AdmittedSense(10, "due", [2, 2]), AdmittedSense(20, "new", [1, 1])],
    )
    return redis, sid, deck


async def test_live_session_reports_round_and_per_sense_progress(session, monkeypatch):
    owner = await _user(session, "sread-live@example.com")
    redis, sid, deck = await _live_session(session, monkeypatch, owner)
    await session_state.pass_checkpoint(redis, sid, 10, required_checkpoints=2)

    read = await read_session(sid, _cu(owner), session)

    assert read.status == "live"
    assert read.session_id == sid
    assert read.node_id == deck.id
    assert read.round_index == 0
    assert read.max_per_round == 4
    assert read.senses_admitted == 2
    assert read.expires_at is not None
    by_sense = {item.sense_id: item for item in read.senses}
    assert by_sense[10].purpose == "due"
    assert by_sense[10].passed == 1
    assert by_sense[10].required == 2
    assert by_sense[10].terminal is False
    assert by_sense[20].purpose == "new"
    assert by_sense[20].passed == 0


async def test_the_read_mutates_nothing(session, monkeypatch):
    """Unlike /next, which advances rounds and reserves deliveries."""
    owner = await _user(session, "sread-pure@example.com")
    redis, sid, _deck = await _live_session(session, monkeypatch, owner)
    before_meta = await session_store.get_meta(redis, sid)
    before_progress = await session_store.get_progress(redis, sid, 10)
    before_excluded = await session_store.excluded_ids(redis, sid, 10)

    for _ in range(3):
        await read_session(sid, _cu(owner), session)

    after_meta = await session_store.get_meta(redis, sid)
    assert after_meta.round_index == before_meta.round_index
    assert after_meta.round_count == before_meta.round_count
    assert await session_store.get_progress(redis, sid, 10) == before_progress
    assert await session_store.excluded_ids(redis, sid, 10) == before_excluded
    assert await session_store.get_delivered(redis, sid, 10) is None


async def test_terminal_senses_are_counted_by_how_they_ended(session, monkeypatch):
    owner = await _user(session, "sread-terminal@example.com")
    redis, sid, _deck = await _live_session(session, monkeypatch, owner)
    # 10 completes; 20 burns its retries.
    await session_state.pass_checkpoint(redis, sid, 10, required_checkpoints=2)
    await session_state.pass_checkpoint(redis, sid, 10, required_checkpoints=2)
    await session_state.open_retry(
        redis, sid, 20, requested_level=1, retries_used=3, failed_round=1, max_retries=2
    )

    read = await read_session(sid, _cu(owner), session)

    assert read.senses_completed == 1
    assert read.senses_exhausted == 1


async def test_answer_counts_come_from_the_durable_rows(session, monkeypatch):
    owner = await _user(session, "sread-answers@example.com")
    redis, sid, _deck = await _live_session(session, monkeypatch, owner)
    session.add_all(
        [
            Response(
                user_id=owner.id, session_id=sid, sense_id=10, question_id=1, is_correct=True
            ),
            Response(
                user_id=owner.id, session_id=sid, sense_id=10, question_id=2, is_correct=False
            ),
            # A pending grade is answered but not yet correct — it must not poison
            # the sum with a NULL.
            Response(
                user_id=owner.id, session_id=sid, sense_id=20, question_id=3, is_correct=None
            ),
        ]
    )
    await session.commit()

    read = await read_session(sid, _cu(owner), session)

    assert read.answers_total == 3
    assert read.answers_correct == 1


async def test_recap_survives_completion_after_redis_is_deleted(session, monkeypatch):
    owner = await _user(session, "sread-recap@example.com")
    redis, sid, deck = await _live_session(session, monkeypatch, owner)
    await session_state.pass_checkpoint(redis, sid, 10, required_checkpoints=2)
    await session_state.pass_checkpoint(redis, sid, 10, required_checkpoints=2)
    session.add(
        Response(user_id=owner.id, session_id=sid, sense_id=10, question_id=1, is_correct=True)
    )
    await session.commit()

    # This is the ordering the router relies on: persist, THEN delete the namespace.
    await session_recap.persist(
        session, redis, sid, user_id=owner.id, node_id=deck.id
    )
    await session_store.end_session(redis, sid)
    assert await session_store.get_meta(redis, sid) is None

    read = await read_session(sid, _cu(owner), session)

    assert read.status == "completed"
    assert read.node_id == deck.id
    assert read.senses_admitted == 2
    assert read.senses_completed == 1
    assert read.answers_total == 1
    assert read.answers_correct == 1
    assert read.rounds_used == 1
    assert read.completed_at is not None
    # Live-only fields stay absent rather than reporting zeros that look like state.
    assert read.round_index is None
    assert read.senses == []


async def test_persisting_the_recap_twice_is_idempotent(session, monkeypatch):
    """Both /next and /answers can reach the completion predicate for one session."""
    owner = await _user(session, "sread-twice@example.com")
    redis, sid, deck = await _live_session(session, monkeypatch, owner)

    await session_recap.persist(session, redis, sid, user_id=owner.id, node_id=deck.id)
    await session_recap.persist(session, redis, sid, user_id=owner.id, node_id=deck.id)

    read = await read_session(sid, _cu(owner), session)
    assert read.status == "live" or read.status == "completed"
    assert await session_recap.load(session, owner.id, sid) is not None


async def test_unknown_session_is_not_found(session, monkeypatch):
    owner = await _user(session, "sread-unknown@example.com")
    monkeypatch.setattr(
        redis_module, "_redis", fake_aioredis.FakeRedis(decode_responses=True)
    )

    with pytest.raises(NotFoundError, match="session_not_found"):
        await read_session(uuid.uuid4().hex, _cu(owner), session)


async def test_another_users_live_session_is_not_found(session, monkeypatch):
    owner = await _user(session, "sread-owner@example.com")
    stranger = await _user(session, "sread-stranger@example.com")
    _redis, sid, _deck = await _live_session(session, monkeypatch, owner)

    with pytest.raises(NotFoundError, match="session_not_found"):
        await read_session(sid, _cu(stranger), session)


async def test_another_users_completed_recap_is_not_found(session, monkeypatch):
    owner = await _user(session, "sread-recap-owner@example.com")
    stranger = await _user(session, "sread-recap-stranger@example.com")
    redis, sid, deck = await _live_session(session, monkeypatch, owner)
    await session_recap.persist(session, redis, sid, user_id=owner.id, node_id=deck.id)
    await session_store.end_session(redis, sid)

    with pytest.raises(NotFoundError, match="session_not_found"):
        await read_session(sid, _cu(stranger), session)
