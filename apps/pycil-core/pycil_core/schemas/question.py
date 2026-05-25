"""Pydantic schemas for the questions API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class QuestionRead(BaseModel):
    id: UUID
    definition_id: int
    type: str
    data: dict[str, Any]
    created_at: datetime


class QuestionFetchResponse(BaseModel):
    """Returned by GET /definitions/{id}/question.

    Either `question` is set (cache hit), or `status='pending'` (generation
    enqueued — client should re-poll). Never both.
    """

    question: QuestionRead | None = None
    status: Literal["ready", "pending"]


class QuestionCheckRequest(BaseModel):
    """User-supplied answer payload for POST /questions/{id}/check."""

    selected_index: int = Field(ge=0, le=3)


class QuestionCheckResponse(BaseModel):
    correct: bool
    explanation: str | None = None
    correct_index: int
