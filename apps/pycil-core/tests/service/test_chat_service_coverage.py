"""Direct unit coverage for chat_service.

Pins session creation (private + public deck access + missing deck guard),
get_session shape + None, append_message token accounting (user vs assistant),
get_messages ordering + ownership gate, and the cap helpers.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from pycil_core.services import chat_service


async def _make_deck(session, author_id, *, visibility="PRIVATE", name="Chat Deck") -> str:
    row = (
        await session.execute(
            text(
                "INSERT INTO nodes (author_id, type, name, visibility) "
                "VALUES (:a, 'DECK'::node_type, :n, CAST(:v AS visibility)) RETURNING id"
            ),
            {"a": author_id, "n": name, "v": visibility},
        )
    ).one()
    await session.commit()
    return str(row.id)


# ── create_session ────────────────────────────────────────────────────────


async def test_create_session_no_deck(session, test_user) -> None:
    sid = await chat_service.create_session(
        session, user_id=test_user["id"], deck_id=None
    )
    row = (
        await session.execute(
            text("SELECT user_id, deck_id FROM chat_sessions WHERE id = :i"),
            {"i": sid},
        )
    ).one()
    assert str(row.user_id) == str(test_user["id"])
    assert row.deck_id is None


async def test_create_session_owned_deck(session, test_user) -> None:
    deck_id = await _make_deck(session, test_user["id"], visibility="PRIVATE")
    sid = await chat_service.create_session(
        session, user_id=test_user["id"], deck_id=deck_id
    )
    row = (
        await session.execute(
            text("SELECT deck_id FROM chat_sessions WHERE id = :i"), {"i": sid}
        )
    ).one()
    assert str(row.deck_id) == deck_id


async def test_create_session_public_deck_of_other_user(
    session, test_user, second_user
) -> None:
    """A PUBLIC deck owned by another user is accessible."""
    deck_id = await _make_deck(session, second_user["id"], visibility="PUBLIC")
    sid = await chat_service.create_session(
        session, user_id=test_user["id"], deck_id=deck_id
    )
    assert sid is not None


async def test_create_session_private_deck_of_other_user_raises(
    session, test_user, second_user
) -> None:
    deck_id = await _make_deck(session, second_user["id"], visibility="PRIVATE")
    with pytest.raises(LookupError, match="deck_not_found_or_not_accessible"):
        await chat_service.create_session(
            session, user_id=test_user["id"], deck_id=deck_id
        )


async def test_create_session_missing_deck_raises(session, test_user) -> None:
    with pytest.raises(LookupError):
        await chat_service.create_session(
            session, user_id=test_user["id"], deck_id=uuid4()
        )


# ── get_session ─────────────────────────────────────────────────────────────


async def test_get_session_shape(session, test_user) -> None:
    sid = await chat_service.create_session(
        session, user_id=test_user["id"], deck_id=None
    )
    out = await chat_service.get_session(
        session, session_id=sid, user_id=test_user["id"]
    )
    assert out is not None
    assert out["id"] == str(sid)
    assert out["deck_id"] is None
    assert out["total_input_tokens"] == 0
    assert out["total_output_tokens"] == 0
    assert out["status"] == "active"
    assert out["created_at"]
    assert out["last_message_at"]


async def test_get_session_wrong_user_none(session, test_user, second_user) -> None:
    sid = await chat_service.create_session(
        session, user_id=test_user["id"], deck_id=None
    )
    assert (
        await chat_service.get_session(
            session, session_id=sid, user_id=second_user["id"]
        )
        is None
    )


# ── append_message + token accounting ───────────────────────────────────────


async def test_append_user_message_counts_input_tokens(session, test_user) -> None:
    sid = await chat_service.create_session(
        session, user_id=test_user["id"], deck_id=None
    )
    content = "x" * 40  # 40 // 4 = 10 estimated tokens
    msg_id = await chat_service.append_message(
        session, session_id=sid, role="user", content=content
    )
    assert msg_id is not None
    out = await chat_service.get_session(
        session, session_id=sid, user_id=test_user["id"]
    )
    assert out["total_input_tokens"] == 10
    assert out["total_output_tokens"] == 0


async def test_append_assistant_message_counts_output_tokens(
    session, test_user
) -> None:
    sid = await chat_service.create_session(
        session, user_id=test_user["id"], deck_id=None
    )
    await chat_service.append_message(
        session, session_id=sid, role="assistant", content="y" * 20
    )
    out = await chat_service.get_session(
        session, session_id=sid, user_id=test_user["id"]
    )
    assert out["total_output_tokens"] == 5
    assert out["total_input_tokens"] == 0


async def test_append_short_content_min_one_token(session, test_user) -> None:
    sid = await chat_service.create_session(
        session, user_id=test_user["id"], deck_id=None
    )
    await chat_service.append_message(
        session, session_id=sid, role="user", content="hi"
    )
    out = await chat_service.get_session(
        session, session_id=sid, user_id=test_user["id"]
    )
    assert out["total_input_tokens"] == 1


# ── get_messages ─────────────────────────────────────────────────────────────


async def test_get_messages_ordered_chronologically(session, test_user) -> None:
    sid = await chat_service.create_session(
        session, user_id=test_user["id"], deck_id=None
    )
    await chat_service.append_message(
        session, session_id=sid, role="user", content="first"
    )
    await chat_service.append_message(
        session, session_id=sid, role="assistant", content="second"
    )
    msgs = await chat_service.get_messages(
        session, session_id=sid, user_id=test_user["id"]
    )
    assert [m["content"] for m in msgs] == ["first", "second"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]


async def test_get_messages_not_owner_empty(session, test_user, second_user) -> None:
    sid = await chat_service.create_session(
        session, user_id=test_user["id"], deck_id=None
    )
    await chat_service.append_message(
        session, session_id=sid, role="user", content="hidden"
    )
    msgs = await chat_service.get_messages(
        session, session_id=sid, user_id=second_user["id"]
    )
    assert msgs == []


# ── cap helpers ──────────────────────────────────────────────────────────────


def test_is_input_capped() -> None:
    assert chat_service.is_input_capped(19_999) is False
    assert chat_service.is_input_capped(20_000) is True


def test_output_cap() -> None:
    assert chat_service.output_cap() == 8_000
