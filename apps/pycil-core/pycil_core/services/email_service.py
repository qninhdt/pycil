"""Email transport.

Provider-agnostic interface; concrete impls for Resend and Postmark
selected via EMAIL_PROVIDER env. Each impl posts to the provider's
HTTP API and persists message_id into email_events for webhook
correlation later.
"""
from __future__ import annotations

import json
import logging
from typing import Literal, Protocol
from uuid import UUID

import httpx
from shared.db import EmailEvent
from sqlalchemy.dialects.postgresql import insert
from sqlmodel.ext.asyncio.session import AsyncSession

from pycil_core.config import get_settings

_log = logging.getLogger(__name__)

EmailProvider = Literal["resend", "postmark", "stub"]


class EmailTransport(Protocol):
    async def send(
        self,
        *,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> str: ...


class StubTransport:
    """Logs only — used when EMAIL_PROVIDER unset (dev / CI)."""

    async def send(
        self,
        *,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> str:
        _log.info(
            "email_stub_sent",
            extra={"to": to, "subject": subject[:80]},
        )
        return f"stub-{abs(hash(subject + to))}"


class ResendTransport:
    """Resend.com REST sender."""

    def __init__(self, api_key: str, from_addr: str) -> None:
        self._api_key = api_key
        self._from = from_addr

    async def send(
        self,
        *,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> str:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": self._from,
                    "to": [to],
                    "subject": subject,
                    "text": text_body,
                    "html": html_body or text_body,
                },
            )
            resp.raise_for_status()
        return resp.json()["id"]


def get_transport() -> EmailTransport:
    settings = get_settings()
    provider = getattr(settings, "email_provider", None) or "stub"
    if provider == "resend":
        api_key = getattr(settings, "resend_api_key", None)
        from_addr = getattr(settings, "email_from_address", "noreply@pycil.local")
        if api_key:
            return ResendTransport(api_key, from_addr)
    return StubTransport()


async def record_event(
    session: AsyncSession,
    *,
    provider: str,
    message_id: str,
    event: str,
    user_id: UUID | None,
    payload: dict,
) -> None:
    await session.exec(
        insert(EmailEvent)
        .values(
            provider=provider,
            message_id=message_id,
            event=event,
            user_id=user_id,
            payload=json.loads(json.dumps(payload, default=str)),
        )
        .on_conflict_do_nothing(
            index_elements=[EmailEvent.provider, EmailEvent.message_id, EmailEvent.event]
        )
    )
