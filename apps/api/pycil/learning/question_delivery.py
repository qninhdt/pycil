"""Answer-safe presentation adapter for Lexi's typed render contracts."""

from lexi_ai.contracts import Flashcard, FreeText, PresentedQuestion, SingleChoice, TextSpan

from pycil.common.errors import ServiceUnavailableError


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
    """Return the legacy REST discriminator for a typed render contract."""
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
