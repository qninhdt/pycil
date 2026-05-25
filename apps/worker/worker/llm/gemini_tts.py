"""Gemini Flash TTS client for worker.

Calls Google's text-to-speech endpoint, returns MP3 bytes. Caller uploads
to B2 and persists signed URL into definitions.tts_url JSONB.
"""
from __future__ import annotations

import os

import httpx


_GEMINI_BASE = "https://texttospeech.googleapis.com/v1/text:synthesize"


_VOICE_BY_LANG = {
    "en": ("en-US", "en-US-Neural2-D"),
    "vi": ("vi-VN", "vi-VN-Neural2-A"),
    "ja": ("ja-JP", "ja-JP-Neural2-B"),
    "ko": ("ko-KR", "ko-KR-Neural2-A"),
    "es": ("es-ES", "es-ES-Neural2-B"),
    "fr": ("fr-FR", "fr-FR-Neural2-A"),
    "de": ("de-DE", "de-DE-Neural2-B"),
}


async def synthesize(text: str, lang: str) -> bytes:
    """Return MP3 bytes for the given text in the given language.

    Raises RuntimeError if the API key is missing or the call fails.
    """
    api_key = os.getenv("GEMINI_TTS_KEY") or os.getenv("GOOGLE_TTS_KEY")
    if not api_key:
        raise RuntimeError("tts_not_configured")

    code, voice = _VOICE_BY_LANG.get(lang, _VOICE_BY_LANG["en"])
    payload = {
        "input": {"text": text[:4000]},
        "voice": {"languageCode": code, "name": voice},
        "audioConfig": {"audioEncoding": "MP3"},
    }
    url = f"{_GEMINI_BASE}?key={api_key}"

    async with httpx.AsyncClient(timeout=20.0) as client:
        res = await client.post(url, json=payload)
        if res.status_code >= 400:
            raise RuntimeError(f"tts_http_{res.status_code}")
        data = res.json()

    audio_b64 = data.get("audioContent")
    if not audio_b64:
        raise RuntimeError("tts_empty_response")
    import base64

    return base64.b64decode(audio_b64)
