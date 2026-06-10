"""LLM output sanitization.

Implementation moved to ``shared.questions.sanitize`` so question plugins can
sanitize their own persisted fields. This module re-exports for backward
compatibility with existing worker imports (``from worker.sanitize import ...``).
"""
from __future__ import annotations

from shared.questions.sanitize import (
    sanitize_answer,
    sanitize_answer_list,
    sanitize_list,
    sanitize_text,
)

__all__ = [
    "sanitize_text",
    "sanitize_list",
    "sanitize_answer",
    "sanitize_answer_list",
]
