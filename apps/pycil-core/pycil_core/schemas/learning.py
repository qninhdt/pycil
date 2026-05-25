"""Pydantic schemas for the learning API."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class StartSessionRequest(BaseModel):
    session_size: int = Field(default=20, ge=1, le=100)


class StartSessionResponse(BaseModel):
    session_id: str
    deck_id: UUID
    selected_count: int


class SessionQuestionResponse(BaseModel):
    """Returned by GET /sessions/{id}/question.

    Either `question` is populated (ready), or `status='pending'` and the UI
    should retry shortly (LLM still generating).
    """

    question: dict[str, Any] | None = None
    status: str  # "ready" | "pending" | "session_complete"
    round_index: int = 0
    round_position: int = 0
    round_size: int = 0


class SubmitAnswerRequest(BaseModel):
    question_id: UUID
    selected_index: int = Field(ge=0, le=3)


class TermReviewedResult(BaseModel):
    definition_id: int
    elo_old: int
    elo_new: int
    elo_delta: int
    next_review_date: datetime
    interval_seconds: int
    mastery_level: int


class SubmitAnswerResponse(BaseModel):
    correct: bool
    explanation: str | None = None
    correct_index: int
    round_complete: bool = False
    session_complete: bool = False
    term_reviewed: TermReviewedResult | None = None
