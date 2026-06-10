"""Session-state load/save edge cases on `learning_service`.

Pinned:
- Missing key → 404 `session_not_found`.
- Corrupt JSON → 500 `session_corrupt`, no crash.
- Round-up via `_save_state` round-trips through Redis verbatim.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from pycil_core.services.learning import session_state as ls
from tests.factories import make_session_state


async def test_load_state_missing_returns_404(fakeredis_client) -> None:
    with pytest.raises(HTTPException) as exc:
        await ls._load_state(fakeredis_client, "no-such-session")
    assert exc.value.status_code == 404


async def test_load_state_corrupt_json_returns_500(fakeredis_client) -> None:
    sid = "corrupt-1"
    await fakeredis_client.set(ls._session_key(sid), "{not-valid-json")

    with pytest.raises(HTTPException) as exc:
        await ls._load_state(fakeredis_client, sid)
    assert exc.value.status_code == 500
    assert "session_corrupt" in str(exc.value.detail)


async def test_save_load_round_trip(fakeredis_client) -> None:
    sid = str(uuid4())
    state = make_session_state(
        session_id=sid,
        user_id=uuid4(),
        deck_id=uuid4(),
        definition_ids=[1, 2, 3],
    )
    await ls._save_state(fakeredis_client, sid, state)

    loaded = await ls._load_state(fakeredis_client, sid)
    assert loaded["id"] == state["id"]
    assert loaded["definition_ids"] == [1, 2, 3]
    assert loaded["round_queue"] == [1, 2, 3]
    assert loaded["term_tracking"]["1"]["completed"] is False
