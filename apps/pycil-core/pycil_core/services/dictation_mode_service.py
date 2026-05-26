"""Listening / dictation mode (P7 phase 2).

Plays the example sentence (or definition) audio via existing TTS pipeline
and asks the user to type what they hear. Falls back to definition text
when TTS is unavailable for the example.

Uses the existing translate_tts_service for audio URLs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class DictationPrompt:
    definition_id: int
    audio_url: str | None
    expected: str
    hint: str | None


async def next_prompts(
    session: AsyncSession, user_id: UUID, deck_id: UUID, limit: int = 10
) -> Sequence[DictationPrompt]:
    rows = (
        await session.execute(
            text(
                """
                SELECT d.id AS definition_id,
                       d.canonical_meaning,
                       t.value AS term_value,
                       (SELECT value FROM term_example_sentences
                         WHERE definition_id = d.id
                         ORDER BY id ASC LIMIT 1) AS example,
                       (SELECT audio_url FROM tts_audio
                         WHERE definition_id = d.id
                         ORDER BY id DESC LIMIT 1) AS audio_url
                  FROM deck_terms dt
                  JOIN terms t ON t.id = dt.term_id
                  JOIN definitions d ON d.term_id = t.id AND d.is_primary
             LEFT JOIN user_term_stats uts
                    ON uts.user_id = :u AND uts.term_id = t.id
                 WHERE dt.deck_id = :d
                   AND COALESCE(uts.status::text, 'active') = 'active'
                 ORDER BY RANDOM()
                 LIMIT :n
                """
            ),
            {"u": user_id, "d": deck_id, "n": limit},
        )
    ).all()
    return [
        DictationPrompt(
            definition_id=int(r.definition_id),
            audio_url=r.audio_url,
            expected=r.example or r.term_value,
            hint=r.canonical_meaning[:60] + "..." if r.canonical_meaning else None,
        )
        for r in rows
    ]
