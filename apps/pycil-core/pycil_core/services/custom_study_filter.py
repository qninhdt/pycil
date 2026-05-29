"""Saved searches / smart deck filter dataclass (P5 phase 2 + P3 phase 4).

Defines the canonical SelectionCriteria dataclass that custom-study,
smart-deck saved searches, and learning-mode filtering all consume.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import UUID


@dataclass
class CustomStudyFilter:
    """Selector for arbitrary slices of a user's term universe.

    All fields are optional; missing means "no constraint".
    Combined with AND across fields; OR within list values.
    """

    deck_ids: list[UUID] = field(default_factory=list)
    cefr_levels: list[str] = field(default_factory=list)
    parts_of_speech: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    elo_min: int | None = None
    elo_max: int | None = None
    last_seen_before_days: int | None = None
    last_seen_after_days: int | None = None
    sources: list[str] = field(default_factory=list)
    limit: int = 50

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["deck_ids"] = [str(x) for x in self.deck_ids]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CustomStudyFilter:
        return cls(
            deck_ids=[UUID(x) for x in d.get("deck_ids") or []],
            cefr_levels=list(d.get("cefr_levels") or []),
            parts_of_speech=list(d.get("parts_of_speech") or []),
            statuses=list(d.get("statuses") or []),
            elo_min=d.get("elo_min"),
            elo_max=d.get("elo_max"),
            last_seen_before_days=d.get("last_seen_before_days"),
            last_seen_after_days=d.get("last_seen_after_days"),
            sources=list(d.get("sources") or []),
            limit=int(d.get("limit") or 50),
        )


def build_where_clause(f: CustomStudyFilter) -> tuple[str, dict[str, Any]]:
    """Return parameterized SQL WHERE clause for the filter.

    Caller composes against `user_term_stats uts JOIN deck_terms dt ON ...
    JOIN definitions d ON ... JOIN terms t ON ...` already.
    """
    parts: list[str] = []
    params: dict[str, Any] = {}
    if f.deck_ids:
        parts.append("dt.deck_id = ANY(:deck_ids)")
        params["deck_ids"] = [str(x) for x in f.deck_ids]
    if f.cefr_levels:
        parts.append("d.cefr_level::text = ANY(:cefr_levels)")
        params["cefr_levels"] = f.cefr_levels
    if f.parts_of_speech:
        parts.append("d.part_of_speech::text = ANY(:pos)")
        params["pos"] = f.parts_of_speech
    if f.statuses:
        parts.append("uts.status::text = ANY(:statuses)")
        params["statuses"] = f.statuses
    if f.elo_min is not None:
        parts.append("uts.elo >= :elo_min")
        params["elo_min"] = f.elo_min
    if f.elo_max is not None:
        parts.append("uts.elo <= :elo_max")
        params["elo_max"] = f.elo_max
    if f.last_seen_before_days is not None:
        parts.append(
            "(uts.last_seen_at IS NULL OR "
            "uts.last_seen_at < NOW() - make_interval(days => :before_days))"
        )
        params["before_days"] = f.last_seen_before_days
    if f.last_seen_after_days is not None:
        parts.append(
            "uts.last_seen_at >= NOW() - make_interval(days => :after_days)"
        )
        params["after_days"] = f.last_seen_after_days
    if f.sources:
        parts.append("t.source = ANY(:sources)")
        params["sources"] = f.sources
    where = " AND ".join(parts) if parts else "TRUE"
    return where, params
