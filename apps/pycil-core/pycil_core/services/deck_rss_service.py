"""Public deck RSS feed (P10 phase 5).

Exposes a per-deck-author RSS 2.0 feed of the user's recent public-deck
activity. Subscribers (e.g. teachers, classmates) can follow updates in a
feed reader without an account.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Sequence
from uuid import UUID
from xml.sax.saxutils import escape

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _rss_date(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt)


async def render_user_feed(
    session: AsyncSession,
    user_id: UUID,
    *,
    site_url: str,
    limit: int = 50,
) -> str:
    user = (
        await session.execute(
            text("SELECT username, display_name FROM users WHERE id = :id"),
            {"id": user_id},
        )
    ).first()
    if not user or not user.username:
        return _empty_feed(site_url, "Pycil user")
    decks = (
        await session.execute(
            text(
                """
                SELECT id, name, created_at, updated_at, definition_count
                  FROM nodes
                 WHERE author_id = :u AND type = 'DECK' AND is_public
                 ORDER BY updated_at DESC
                 LIMIT :n
                """
            ),
            {"u": user_id, "n": limit},
        )
    ).all()
    return _build_feed(
        site_url=site_url,
        author_username=user.username,
        author_display=user.display_name or user.username,
        items=decks,
    )


def _build_feed(
    *, site_url: str, author_username: str, author_display: str, items: Sequence
) -> str:
    title = f"{author_display} on Pycil"
    link = f"{site_url}/u/{author_username}"
    description = f"Recent public decks by {author_display}"
    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "<channel>",
        f"<title>{escape(title)}</title>",
        f"<link>{escape(link)}</link>",
        f"<description>{escape(description)}</description>",
    ]
    for d in items:
        item_url = f"{site_url}/decks/{d.id}"
        item_desc = f"{d.definition_count or 0} terms"
        parts.extend(
            [
                "<item>",
                f"<title>{escape(d.name)}</title>",
                f"<link>{escape(item_url)}</link>",
                f"<guid>{escape(item_url)}</guid>",
                f"<pubDate>{_rss_date(d.updated_at)}</pubDate>",
                f"<description>{escape(item_desc)}</description>",
                "</item>",
            ]
        )
    parts.extend(["</channel>", "</rss>"])
    return "\n".join(parts)


def _empty_feed(site_url: str, name: str) -> str:
    return _build_feed(
        site_url=site_url,
        author_username="anonymous",
        author_display=name,
        items=[],
    )
