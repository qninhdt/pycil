"""Question lookup and typed, API-safe delivery helpers."""

from pycil.common.errors import ServiceUnavailableError
from pycil.content.lexi_port import LexiClient
from pycil.content.lexi_types import Question


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
    """Create one format-specific, answer-free frontend presentation.

    Lexi already sends a presentation projection over HTTP. The explicit
    allowlist below remains a second boundary: fake/misconfigured providers can
    never leak correct indices, rubric text, accepted forms, or arbitrary JSON.
    """
    if question.id is None or question.sense_id is None:
        raise ValueError("question_requires_id_and_sense")
    payload = question.payload
    try:
        if question.format in {"definition_mcq", "contextual_mcq"}:
            presentation = {"stem": payload["stem"], "options": payload["options"]}
        elif question.format == "cloze":
            presentation = {"stem_with_blank": payload["stem_with_blank"]}
        elif question.format == "use_in_sentence":
            presentation = {"prompt": payload["prompt"]}
        else:
            raise KeyError("format")
    except (KeyError, TypeError) as exc:
        raise ServiceUnavailableError("lexi_question_presentation_invalid") from exc
    return {
        "question_id": question.id,
        "sense_id": question.sense_id,
        "recommended_type": recommended_type,
        "format": question.format,
        "payload": presentation,
    }
