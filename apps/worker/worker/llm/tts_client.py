"""TTS synth client for worker.

Calls OpenRouter's OpenAI-compatible /audio/speech endpoint and returns raw
MP3 bytes. The caller uploads to S3 and persists the signed URL into
definitions.tts_url JSONB.

Reuses OPENROUTER_API_KEY — no separate TTS provider secret. Voice/model are
env-overridable; a single voice is used for all languages (OpenRouter TTS
voices are model-scoped, not BCP-47 language codes).
"""
from __future__ import annotations

import os

import httpx


_SPEECH_URL = "https://openrouter.ai/api/v1/audio/speech"
_DEFAULT_MODEL = "openai/gpt-4o-mini-tts"
_DEFAULT_VOICE = "alloy"


async def synthesize(text: str, lang: str) -> bytes:
    """Return MP3 bytes for the given text. `lang` is accepted for call-site
    compatibility but unused — voice is model-scoped, not per-language.

    Raises RuntimeError if the key is missing or the call fails.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("tts_not_configured")

    payload = {
        "model": os.getenv("OPENROUTER_TTS_MODEL", _DEFAULT_MODEL),
        "input": text[:4000],
        "voice": os.getenv("OPENROUTER_TTS_VOICE", _DEFAULT_VOICE),
        "response_format": "mp3",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            _SPEECH_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        if res.status_code >= 400:
            raise RuntimeError(f"tts_http_{res.status_code}")
        audio = res.content

    if not audio:
        raise RuntimeError("tts_empty_response")
    return audio
