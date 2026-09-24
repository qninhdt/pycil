"""Answer-safe presentation adapter for Lexi's typed render contracts.

Also owns the mapping from a resolved question to its wire shape. That lived in the
router as a private helper, which meant the one place that decides what a learner is
allowed to see was mixed in with routing — and the answer key is exactly what must
not leak, so it belongs next to the payload mapping that strips it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from lexi_ai.contracts import (
    Flashcard,
    FreeText,
    PresentedQuestion,
    RenderKind,
    SingleChoice,
    TextSpan,
)
from redis.asyncio import Redis

from pycil.common.errors import ServiceUnavailableError
from pycil.learning import session_store
from pycil.learning.resolver import ResolvedQuestion
from pycil.learning.schemas import (
    FlashcardReady,
    FreeTextReady,
    ReadyQuestion,
    SingleChoiceReady,
    TextSpanReady,
)
from pycil.learning.session_store import SenseProgress

_READY_CLASSES = {
    "flashcard": FlashcardReady,
    "single_choice": SingleChoiceReady,
    "text_span": TextSpanReady,
    "free_text": FreeTextReady,
}


def presentation_payload(question: PresentedQuestion) -> dict:
    """Map a typed, answer-free render contract to the existing REST payload."""
    try:
        render_kind = question.render_kind
    except AttributeError as err:
        raise ServiceUnavailableError("lexi_question_presentation_invalid") from err
    if render_kind is RenderKind.SINGLE_CHOICE:
        render = cast(SingleChoice, question.render)
        return {"stem": render.stem, "options": list(render.options)}
    if question.render_kind is RenderKind.TEXT_SPAN:
        render = cast(TextSpan, question.render)
        return {
            "stem_with_blank": render.stem_with_blank,
            "word_bank": list(render.word_bank),
        }
    if question.render_kind is RenderKind.FREE_TEXT:
        render = cast(FreeText, question.render)
        return {"prompt": render.prompt}
    if question.render_kind is RenderKind.FLASHCARD:
        render = cast(Flashcard, question.render)
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
    try:
        return question.render_kind.value
    except AttributeError as err:
        raise ServiceUnavailableError("lexi_render_format_unsupported") from err


def ready_question(resolved: ResolvedQuestion) -> ReadyQuestion:
    """Build the wire shape for a delivered question, carrying no answer key.

    An exposure has no assessment id: it is a flashcard the learner reads, never
    submits, so its wire ``question_id`` is None. Everything else is already an
    integer from Lexi's pinned contract.
    """
    question = resolved.question
    format_name = render_format(question)
    ready_cls = _READY_CLASSES.get(format_name)
    if ready_cls is None:
        raise ServiceUnavailableError("lexi_render_format_unsupported")
    if question.sense_id is None:
        raise ServiceUnavailableError("lexi_question_presentation_invalid")
    question_id = None if question.interaction == "exposure" else question.question_id
    return ready_cls(
        question_id=question_id,
        sense_id=question.sense_id,
        interaction_mode=question.interaction,
        requested_level=resolved.requested_level,
        served_level=resolved.served_level,
        is_fallback=resolved.is_fallback,
        is_graded=resolved.is_graded,
        payload=presentation_payload(question),
    )


@dataclass(frozen=True)
class Requirement:
    sense_id: int
    kind: str  # "exposure" | "grade" | "reask"
    requested_level: int


def eligible_requirement(
    purpose: str,
    progress: SenseProgress,
    current_round: int,
    *,
    graded: bool,
) -> Requirement | None:
    """Return the one item this sense may contribute to this round."""
    if progress.terminal or progress.current_qid is not None:
        return None
    if progress.last_round_used >= current_round:
        return None

    if purpose == "new" and not progress.exposed:
        return Requirement(progress.sense_id, "exposure", 0)
    if not graded:
        return Requirement(progress.sense_id, "grade", progress.requested_level)
    if (
        progress.reask_pending
        and not progress.reask_done
        and progress.reask_failed_round is not None
        and progress.reask_failed_round < current_round
        and progress.reask_level is not None
    ):
        return Requirement(progress.sense_id, "reask", progress.reask_level)
    return None


async def round_candidates(
    redis: Redis, session_id: str, current_round: int
) -> list[Requirement]:
    """Return eligible items; callers shuffle this bounded list per round."""
    admitted = await session_store.get_admitted(redis, session_id)
    graded = await session_store.graded_senses(redis, session_id)
    requirements: list[Requirement] = []
    for sense_id, purpose in admitted.items():
        progress = await session_store.get_progress(redis, session_id, sense_id)
        if progress is None:
            continue
        requirement = eligible_requirement(
            purpose,
            progress,
            current_round,
            graded=sense_id in graded,
        )
        if requirement is not None:
            requirements.append(requirement)
    return requirements


async def has_open_work(redis: Redis, session_id: str) -> bool:
    """Return whether an admitted sense still needs delivery or an answer."""
    for sense_id in await session_store.get_admitted(redis, session_id):
        progress = await session_store.get_progress(redis, session_id, sense_id)
        if progress is not None and not progress.terminal:
            return True
    return False


async def session_complete(redis: Redis, session_id: str) -> bool:
    """All admitted senses are terminal; no async grade state exists to await."""
    admitted = await session_store.get_admitted(redis, session_id)
    if not admitted:
        return True
    for sense_id in admitted:
        progress = await session_store.get_progress(redis, session_id, sense_id)
        if progress is None or not progress.terminal:
            return False
    return True
