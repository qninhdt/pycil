"""Server-only HMAC work-key helpers for generic async tasks."""

import base64
import hashlib
import hmac


def opaque_content_hmac(secret: str, value: str) -> str:
    """Return URL-safe deterministic identity without exposing source text."""
    digest = hmac.new(secret.encode(), value.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def word_work_key(match_key: str, dataset_fingerprint: str) -> str:
    return f"word:{match_key}:{dataset_fingerprint}"


def question_pool_work_key(
    sense_id: int, question_format: str, generator_revision: str, pool_generation: int
) -> str:
    return f"question-pool:{sense_id}:{question_format}:{generator_revision}:{pool_generation}"


def translation_work_key(
    source_identity: str, content_hmac: str, locale: str, revision: str
) -> str:
    return f"translation:{source_identity}:{content_hmac}:{locale}:{revision}"


def tts_work_key(
    source_identity: str, content_hmac: str, voice: str, output_format: str, revision: str
) -> str:
    return f"tts:{source_identity}:{content_hmac}:{voice}:{output_format}:{revision}"


def grading_work_key(response_id: str) -> str:
    return f"grading:{response_id}"
