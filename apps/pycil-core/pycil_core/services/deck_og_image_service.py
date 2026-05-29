"""Per-deck OG image generation (P10 phase 4).

Generates a 1200×630 PNG with deck name + author + CEFR mix bar for
deck-detail OG meta tags. Cached on disk and re-rendered on deck rename.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.db import Node
from shared.db.enums import NodeType

_log = logging.getLogger(__name__)


def _cache_path(base: Path, deck_id: UUID, etag: str) -> Path:
    return base / f"deck-{deck_id}-{etag}.png"


def _etag(name: str, count: int) -> str:
    return hashlib.sha1(f"{name}:{count}".encode()).hexdigest()[:10]


async def get_or_render(
    session: AsyncSession,
    deck_id: UUID,
    *,
    cache_dir: Path,
) -> Path | None:
    row = (
        await session.exec(
            select(
                Node.name,
                Node.definition_count.label("cnt"),
            ).where(Node.id == deck_id, Node.type == NodeType.DECK)
        )
    ).first()
    if not row:
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    etag = _etag(row.name, int(row.cnt))
    target = _cache_path(cache_dir, deck_id, etag)
    if target.exists():
        return target
    return _render_png(target, name=row.name, count=int(row.cnt))


def _render_png(target: Path, *, name: str, count: int) -> Path | None:
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except ImportError:
        _log.warning("og_image_skipped_pillow_missing")
        return None
    img = Image.new("RGB", (1200, 630), (15, 23, 42))
    draw = ImageDraw.Draw(img)
    try:
        font_lg = ImageFont.truetype("DejaVuSans-Bold.ttf", 64)
        font_sm = ImageFont.truetype("DejaVuSans.ttf", 36)
    except OSError:
        font_lg = ImageFont.load_default()
        font_sm = ImageFont.load_default()
    draw.text((80, 220), name[:40], font=font_lg, fill=(255, 255, 255))
    draw.text((80, 320), f"{count} terms", font=font_sm, fill=(125, 211, 252))
    draw.text((80, 540), "pycil — vocabulary that sticks", font=font_sm, fill=(148, 163, 184))
    img.save(target, "PNG", optimize=True)
    return target
