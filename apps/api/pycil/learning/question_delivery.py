"""Question lookup and API-safe delivery helpers.

Question content stays authoritative in lexi-ai.  This module has one narrow
boundary: it accepts only a question selected server-side and strips every
answer-bearing field before a payload crosses the API boundary.
"""

from typing import Any

from lexi_ai.read_models import Question

from pycil.content.lexi_port import LexiClient

_SAFE_PAYLOAD_KEYS = {
    "audio",
    "audiourl",
    "blank",
    "choices",
    "context",
    "hint",
    "image",
    "imageurl",
    "instructions",
    "items",
    "label",
    "options",
    "prompt",
    "question",
    "sentence",
    "text",
}


def _is_safe_key(key: str) -> bool:
    normalized = "".join(character for character in key.lower() if character.isalnum())
    return normalized in _SAFE_PAYLOAD_KEYS


def sanitize_payload(value: Any) -> Any:
    """Remove answer material recursively, including nested generator metadata."""
    if isinstance(value, dict):
        return {
            key: sanitize_payload(item)
            for key, item in value.items()
            if _is_safe_key(key)
        }
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    return value


async def find_question(
    client: LexiClient, sense_id: int, recommended_type: str
) -> Question | None:
    """Look up an existing question through the optional Phase-3 port seam.

    Older lexi deployments have no sense-format lookup yet.  They intentionally
    yield ``None`` so session delivery remains a typed pending state rather than
    guessing a question or leaking an arbitrary one.
    """
    lookup = getattr(client, "get_question_for_sense", None)
    if lookup is None:
        return None
    return await lookup(sense_id, recommended_type)


def ready_payload(question: Question, recommended_type: str) -> dict:
    if question.id is None or question.sense_id is None:
        raise ValueError("question_requires_id_and_sense")
    return {
        "question_id": question.id,
        "sense_id": question.sense_id,
        "recommended_type": recommended_type,
        "payload": sanitize_payload(question.payload),
    }
