"""Reload before and after finish, and the recap that outlives Redis.

The phase requires three behaviours that only appear across a session's lifetime:
a reload mid-session returns the same unconsumed item; finishing persists a recap
and deletes the Redis document; and a reload *after* finishing returns the completed
recap rather than a 404. The last one is the interesting case, because the live state
the recap describes has been deliberately deleted by then.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from pycil.auth.models import User
from pycil.learning import recap, session_store
from pycil.learning.models import Response, SessionSummary

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


async def _user(session, email: str) -> User:
    user = User(email=email, clerk_id=f"user_{email}")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _deck(session, owner_id):
    """A real node: `session_summaries.node_id` is a foreign key, not a free UUID."""
    from pycil.hierarchy.application import service as hierarchy_service
    from pycil.hierarchy.infra.models import NodeType

    return await hierarchy_service.create_node(
        session, owner_id, node_type=NodeType.DECK, name="recap deck"
    )


async def _session(redis, owner_id, node_id, *, target_words: int = 5, max_per_round: int = 5):
    session_id = uuid4().hex
    await session_store.create(
        redis,
        session_id,
        owner_id=owner_id,
        node_id=node_id,
        scope_generation=1,
        target_words=target_words,
        max_per_round=max_per_round,
        admitted=[
            session_store.AdmittedSense(sense_id=sense_id, purpose="new", requested_level=1)
            for sense_id in (41, 42)
        ],
    )
    return session_id


async def test_a_reload_returns_the_same_unconsumed_item(session, fake_redis):
    """Reading the session must not consume the delivery it reports."""
    user = await _user(session, "reload@example.test")
    deck = await _deck(session, user.id)
    session_id = await _session(fake_redis, user.id, deck.id)
    await session_store.set_delivered(fake_redis, session_id, 41, 7, kind="grade", round_index=0)

    first = await session_store.get_delivery(fake_redis, session_id, 41)
    second = await session_store.get_delivery(fake_redis, session_id, 41)

    assert first is not None and second is not None
    assert (first.question_id, second.question_id) == (7, 7)
    assert first.kind == "grade"


async def test_finishing_persists_a_recap_and_removes_the_session_document(
    session, fake_redis
):
    """The recap is written while the live state still exists, then the key goes."""
    user = await _user(session, "recap@example.test")
    deck = await _deck(session, user.id)
    session_id = await _session(fake_redis, user.id, deck.id)

    session.add(
        Response(
            user_id=user.id,
            session_id=session_id,
            sense_id=41,
            question_id=7,
            requested_level=1,
            served_level=1,
            is_correct=True,
            idempotency_key=f"{session_id}:41",
        )
    )
    session.add(
        Response(
            user_id=user.id,
            session_id=session_id,
            sense_id=42,
            question_id=8,
            requested_level=1,
            served_level=1,
            is_correct=False,
            idempotency_key=f"{session_id}:42",
        )
    )
    await session.commit()

    await recap.persist(
        session, fake_redis, session_id, user_id=user.id, node_id=deck.id
    )
    await session_store.end_session(fake_redis, session_id)

    assert await session_store.get_meta(fake_redis, session_id) is None, (
        "the disposable document is gone once the session is finished"
    )
    summary = await recap.load(session, user.id, session_id)
    assert summary is not None, "the recap must outlive the Redis document"
    assert summary.answers_total == 2
    assert summary.answers_correct == 1


async def test_the_recap_is_idempotent_across_repeated_completion(session, fake_redis):
    """Both /next and /answers can observe completion, so the write is an upsert."""
    user = await _user(session, "recap-twice@example.test")
    deck = await _deck(session, user.id)
    session_id = await _session(fake_redis, user.id, deck.id)

    await recap.persist(
        session, fake_redis, session_id, user_id=user.id, node_id=deck.id
    )
    await recap.persist(
        session, fake_redis, session_id, user_id=user.id, node_id=deck.id
    )

    count = await session.scalar(
        select(func.count()).select_from(SessionSummary).where(
            SessionSummary.session_id == session_id
        )
    )
    assert count == 1, "one session has exactly one recap row"


async def test_a_recap_counts_a_pending_answer_without_calling_it_correct(
    session, fake_redis
):
    """An ungraded answer is answered but not correct, and must not 500 the recap.

    ``SUM`` over a set of NULLs returns NULL rather than 0, which would reach
    ``int(None)`` — the reason the query coalesces.
    """
    user = await _user(session, "recap-pending@example.test")
    deck = await _deck(session, user.id)
    session_id = await _session(fake_redis, user.id, deck.id)
    session.add(
        Response(
            user_id=user.id,
            session_id=session_id,
            sense_id=41,
            question_id=7,
            requested_level=1,
            served_level=1,
            is_correct=None,
            idempotency_key=f"{session_id}:41",
        )
    )
    await session.commit()

    total, correct = await recap.answer_counts(session, user.id, session_id)
    assert (total, correct) == (1, 0)


async def test_an_expired_session_reports_missing_but_keeps_committed_answers(
    session, fake_redis
):
    """Losing the document may end a live session; it cannot erase learning."""
    user = await _user(session, "expired@example.test")
    deck = await _deck(session, user.id)
    session_id = await _session(fake_redis, user.id, deck.id)
    session.add(
        Response(
            user_id=user.id,
            session_id=session_id,
            sense_id=41,
            question_id=7,
            requested_level=1,
            served_level=1,
            is_correct=True,
            idempotency_key=f"{session_id}:41",
        )
    )
    await session.commit()

    await fake_redis.flushall()  # simulate expiry of the 24-hour document

    assert await session_store.get_meta(fake_redis, session_id) is None
    total, correct = await recap.answer_counts(session, user.id, session_id)
    assert (total, correct) == (1, 1), (
        "the committed answer is still counted after the session state is gone"
    )
