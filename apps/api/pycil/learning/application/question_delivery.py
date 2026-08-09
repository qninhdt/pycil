"""Answer-safe presentation adapter for Lexi's typed render contracts.

Also owns the mapping from a resolved question to its wire shape. That lived in the
router as a private helper, which meant the one place that decides what a learner is
allowed to see was mixed in with routing — and the answer key is exactly what must
not leak, so it belongs next to the payload mapping that strips it.
"""

from lexi_ai.contracts import Flashcard, FreeText, PresentedQuestion, SingleChoice, TextSpan

from pycil.common.errors import ServiceUnavailableError
from pycil.learning.domain.resolver import ResolvedQuestion
from pycil.learning.domain.schemas import (
    FlashcardReady,
    FreeTextReady,
    ReadyQuestion,
    SingleChoiceReady,
    TextSpanReady,
)

_READY_CLASSES = {
    "flashcard": FlashcardReady,
    "single_choice": SingleChoiceReady,
    "text_span": TextSpanReady,
    "free_text": FreeTextReady,
}


def presentation_payload(question: PresentedQuestion) -> dict:
    """Map a typed, answer-free render contract to the existing REST payload."""
    render = question.render
    if isinstance(render, SingleChoice):
        return {"stem": render.stem, "options": list(render.options)}
    if isinstance(render, TextSpan):
        return {
            "stem_with_blank": render.stem_with_blank,
            "word_bank": list(render.word_bank),
        }
    if isinstance(render, FreeText):
        return {"prompt": render.prompt}
    if isinstance(render, Flashcard):
        return {
            "word": render.word,
            "definition": render.definition,
            "pos": render.pos,
            "example": render.example,
            "ipa_uk": render.ipa_uk,
            "ipa_us": render.ipa_us,
        }
    raise ServiceUnavailableError("lexi_question_presentation_invalid")



def render_format(question: PresentedQuestion) -> str:
    """The wire discriminator for a typed render contract.

    This is what `answering.py` puts on every delivered question and what the client switches
    on to pick a component. The typed `render` object is the internal
    representation; this is its name on the wire, and the two are deliberately
    separate so an internal type can be refactored without a wire break.
    """
    render = question.render
    if isinstance(render, SingleChoice):
        return "single_choice"
    if isinstance(render, TextSpan):
        return "text_span"
    if isinstance(render, FreeText):
        return "free_text"
    if isinstance(render, Flashcard):
        return "flashcard"
    raise ServiceUnavailableError("lexi_render_format_unsupported")


def ready_question(resolved: ResolvedQuestion) -> ReadyQuestion:
    """Build the wire shape for a delivered question, carrying no answer key.

    An exposure has no assessment id: it is a flashcard the learner reads, never
    submits, so its ``question_id`` is None rather than a value a client could post
    back. Everything else must be integer-compatible, because that is what
    ``/answers`` accepts on the wire.
    """
    question = resolved.question
    format_name = render_format(question)
    ready_cls = _READY_CLASSES.get(format_name)
    if ready_cls is None:
        raise ServiceUnavailableError("lexi_render_format_unsupported")
    if question.sense_id is None:
        raise ServiceUnavailableError("lexi_question_presentation_invalid")
    try:
        sense_id = int(question.sense_id)
        question_id = (
            None if question.interaction == "exposure" else int(question.question_id)
        )
    except (TypeError, ValueError) as err:
        raise ServiceUnavailableError("lexi_question_presentation_invalid") from err
    return ready_cls(
        question_id=question_id,
        sense_id=sense_id,
        interaction_mode=question.interaction,
        requested_level=resolved.requested_level,
        served_level=resolved.served_level,
        is_fallback=resolved.is_fallback,
        payload=presentation_payload(question),
    )
