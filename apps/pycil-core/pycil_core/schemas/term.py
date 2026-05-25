"""Pydantic schemas for terms."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TermAddRequest(BaseModel):
    value: str = Field(min_length=1, max_length=64)


class TermRead(BaseModel):
    id: int
    value: str
    type: str
    created_at: datetime
    updated_at: datetime


class TermAddResponse(BaseModel):
    """Returned from POST /decks/{id}/terms.

    Phase 2: just returns the term row. Phase 3 extends with `job_id` for the
    enrichment job.
    """

    term: TermRead
    job_id: str | None = None


class DeckTermRead(BaseModel):
    """One row in `GET /decks/{id}/terms`.

    Carries enough state for the UI to decide between "Generating…" (SSE on
    `job_id`) and rendering the enriched payload (`definition`).
    """

    term: TermRead
    position: int
    definition: dict[str, Any] | None = None
    job_id: str | None = None
    job_status: str | None = None
