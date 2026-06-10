"""Pydantic schemas for the learning API."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class StartSessionRequest(BaseModel):
    session_size: int = Field(default=20, ge=1, le=100)
    # Optional learning theme; validated against the theme catalog. None →
    # themed-pool rotation (a different theme per question) or neutral UI.
    theme_id: str | None = None


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
    # Presentation-only theme for this question (FE skin). None → neutral UI.
    theme: str | None = None


class SubmitAnswerRequest(BaseModel):
    question_id: UUID
    # MCQ-shaped today; the generic {answer: dict} payload (for Write/Fill)
    # lands in phase 5 alongside the FE submit-contract migration. `answer` is
    # the forward-compatible generic payload; when present it takes precedence.
    selected_index: int = Field(default=0, ge=0, le=3)
    answer: dict[str, Any] | None = None


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
    # Generic grading result (type-agnostic). `reveal` carries the plugin's
    # post-submit disclosure (e.g. MCQ correct_index, Write expected_answer);
    # `score` is 0.0..1.0 credit. `feedback` is the human-readable explanation.
    score: float = 0.0
    feedback: str | None = None
    reveal: dict[str, Any] = Field(default_factory=dict)
    # Back-compat derived fields for the current MCQ FE (migrated in phase 5).
    explanation: str | None = None
    correct_index: int = 0
    round_complete: bool = False
    session_complete: bool = False
    term_reviewed: TermReviewedResult | None = None
