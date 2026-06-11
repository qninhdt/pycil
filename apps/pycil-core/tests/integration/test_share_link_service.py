"""Share-link service: token format, idempotent revoke, resolve."""
from __future__ import annotations

import re
import string

from pycil_core.services import share_link_service
from tests.factories import make_deck

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+$")


async def test_create_link_returns_well_formed_token(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])

    result = await share_link_service.create_link(
        session, node_id=deck["id"], created_by=test_user["id"]
    )

    assert _TOKEN_RE.match(result["token"]), result["token"]
    # secrets.token_urlsafe(24) → 32 base64-urlsafe chars (no padding).
    assert len(result["token"]) == 32
    assert "id" in result
    assert "created_at" in result


async def test_create_link_rejects_non_owner(session, test_user, second_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])

    import pytest

    with pytest.raises(LookupError):
        await share_link_service.create_link(
            session, node_id=deck["id"], created_by=second_user["id"]
        )


async def test_revoke_link_is_idempotent(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    link = await share_link_service.create_link(
        session, node_id=deck["id"], created_by=test_user["id"]
    )

    from uuid import UUID

    first = await share_link_service.revoke_link(
        session, link_id=UUID(link["id"]), user_id=test_user["id"]
    )
    second = await share_link_service.revoke_link(
        session, link_id=UUID(link["id"]), user_id=test_user["id"]
    )

    assert first is True
    assert second is False


async def test_resolve_returns_none_after_revoke(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    link = await share_link_service.create_link(
        session, node_id=deck["id"], created_by=test_user["id"]
    )
    from uuid import UUID

    pre = await share_link_service.resolve_token(session, token=link["token"])
    assert pre is not None
    assert pre["node_id"] == str(deck["id"])

    await share_link_service.revoke_link(
        session, link_id=UUID(link["id"]), user_id=test_user["id"]
    )

    post = await share_link_service.resolve_token(session, token=link["token"])
    assert post is None


async def test_token_charset_is_url_safe(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    allowed = set(string.ascii_letters + string.digits + "-_")
    for _ in range(10):
        link = await share_link_service.create_link(
            session, node_id=deck["id"], created_by=test_user["id"]
        )
        assert set(link["token"]).issubset(allowed)
