"""Coverage for email_service (provider selection + transports + event log).

Pinned:
- StubTransport returns a deterministic stub id, no network.
- get_transport: stub by default, Resend when provider+key set, falls back
  to stub when resend selected but key missing.
- ResendTransport posts and returns provider message id; raises on HTTP error.
- record_event persists a row; conflicting (provider,message_id,event) is a no-op.
"""
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from pycil_core.services import email_service as svc

# --- StubTransport ----------------------------------------------------------

async def test_stub_transport_returns_stub_id():
    t = svc.StubTransport()
    mid = await t.send(to="a@b.test", subject="Hi", text_body="body")
    assert mid.startswith("stub-")


# --- get_transport selection ------------------------------------------------
# NOTE: email_provider / resend_api_key are NOT declared fields on Settings;
# get_transport reads them via getattr(..., default). Patch get_settings with a
# lightweight stand-in rather than mutating the (field-locked) pydantic model.


class _FakeSettings:
    def __init__(self, **attrs) -> None:
        self.__dict__.update(attrs)


def _patch_settings(monkeypatch, **attrs) -> None:
    monkeypatch.setattr(svc, "get_settings", lambda: _FakeSettings(**attrs))


def test_get_transport_defaults_to_stub(monkeypatch):
    # No provider attr at all → getattr default "stub" → StubTransport.
    _patch_settings(monkeypatch)
    assert isinstance(svc.get_transport(), svc.StubTransport)


def test_get_transport_resend_with_key(monkeypatch):
    _patch_settings(
        monkeypatch,
        email_provider="resend",
        resend_api_key="re_test",
        email_from_address="x@pycil.test",
    )
    assert isinstance(svc.get_transport(), svc.ResendTransport)


def test_get_transport_resend_missing_key_falls_back_to_stub(monkeypatch):
    _patch_settings(monkeypatch, email_provider="resend", resend_api_key=None)
    assert isinstance(svc.get_transport(), svc.StubTransport)


# --- ResendTransport HTTP plumbing ------------------------------------------

class _Resp:
    def __init__(self, payload: dict, *, exc=None):
        self._p = payload
        self._exc = exc

    def raise_for_status(self):
        if self._exc is not None:
            raise self._exc

    def json(self) -> dict:
        return self._p


def _patch_post(monkeypatch, *, resp):
    captured: dict = {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, *, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return resp

    monkeypatch.setattr(svc.httpx, "AsyncClient", _Client)
    return captured


async def test_resend_send_returns_message_id(monkeypatch):
    captured = _patch_post(monkeypatch, resp=_Resp({"id": "msg-123"}))
    t = svc.ResendTransport("re_key", "from@pycil.test")
    mid = await t.send(
        to="u@b.test", subject="Subj", text_body="hello", html_body="<p>hi</p>"
    )
    assert mid == "msg-123"
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer re_key"
    assert captured["json"]["to"] == ["u@b.test"]
    assert captured["json"]["html"] == "<p>hi</p>"


async def test_resend_send_html_defaults_to_text(monkeypatch):
    captured = _patch_post(monkeypatch, resp=_Resp({"id": "msg-x"}))
    t = svc.ResendTransport("re_key", "from@pycil.test")
    await t.send(to="u@b.test", subject="S", text_body="plain")
    assert captured["json"]["html"] == "plain"


async def test_resend_send_raises_on_http_error(monkeypatch):
    err = httpx.HTTPStatusError(
        "boom", request=httpx.Request("POST", "https://api.resend.com/emails"),
        response=httpx.Response(500),
    )
    _patch_post(monkeypatch, resp=_Resp({}, exc=err))
    t = svc.ResendTransport("re_key", "from@pycil.test")
    with pytest.raises(httpx.HTTPStatusError):
        await t.send(to="u@b.test", subject="S", text_body="plain")


# --- record_event persistence + idempotency ---------------------------------

async def _count(session, message_id: str) -> int:
    row = (
        await session.execute(
            text("SELECT count(*) AS c FROM email_events WHERE message_id = :m"),
            {"m": message_id},
        )
    ).one()
    return int(row.c)


async def test_record_event_persists_row(session, test_user):
    mid = f"msg-{uuid4().hex}"
    await svc.record_event(
        session,
        provider="resend",
        message_id=mid,
        event="delivered",
        user_id=test_user["id"],
        payload={"foo": "bar"},
    )
    await session.commit()
    assert await _count(session, mid) == 1


async def test_record_event_conflict_is_noop(session):
    mid = f"msg-{uuid4().hex}"
    for _ in range(2):
        await svc.record_event(
            session,
            provider="postmark",
            message_id=mid,
            event="opened",
            user_id=None,
            payload={"n": 1},
        )
        await session.commit()
    # Same (provider, message_id, event) → on_conflict_do_nothing → single row.
    assert await _count(session, mid) == 1


async def test_record_event_serializes_non_json_payload(session):
    mid = f"msg-{uuid4().hex}"
    # `default=str` path: a UUID inside payload must serialize, not raise.
    await svc.record_event(
        session,
        provider="resend",
        message_id=mid,
        event="bounced",
        user_id=None,
        payload={"ref": uuid4()},
    )
    await session.commit()
    assert await _count(session, mid) == 1
