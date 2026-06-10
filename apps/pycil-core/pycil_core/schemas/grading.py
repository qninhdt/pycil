"""Schemas for async (SSE-streamed) answer grading."""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AsyncGradePending(BaseModel):
    """Returned by submit/check when the answer needs server-side grading.

    The client opens an SSE stream on ``/jobs/{job_id}/stream`` and, on the
    terminal verdict frame, calls the apply-verdict endpoint with
    ``response_id`` to commit ELO/XP under the session lock.
    """

    grading: Literal["pending"] = "pending"
    job_id: UUID
    response_id: UUID


class ApplyVerdictRequest(BaseModel):
    """Body for the apply-verdict endpoint the FE calls on SSE completion."""

    response_id: UUID


class GradeVerdict(BaseModel):
    """The verdict the grade_answer worker persists + publishes."""

    correct: bool
    score: float = 0.0
    feedback: str | None = None
    reveal: dict[str, Any] = Field(default_factory=dict)
