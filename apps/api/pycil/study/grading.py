"""Read-only diagnostic grading; review submission owns learning progress writes."""

from collections.abc import Sequence
from typing import Protocol, cast

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.infrastructure.kv_store import InMemoryStore
from pycil.infrastructure.observability import get_logger, observe_operation
from pycil.study.artifacts.schemas import Artifact
from pycil.study.artifacts.storage import get_many
from pycil.study.config import GradingPolicy
from pycil.study.decisions import (
    DefinitionAssessment,
    RewriteAssessment,
    TargetUseAssessment,
    UsageAssessment,
    sense_selection_model,
    single_word_model,
)
from pycil.study.enums import (
    ALLOWED_PAIRS,
    QUESTION_ARTIFACT_MAP,
    DefinitionAccuracy,
    DefinitionCoverage,
    MeaningPreservation,
    QuestionType,
    ResponseFormat,
    UsageForm,
    UsageMeaning,
)
from pycil.study.errors import QuestionArtifactNotFoundError, UnsupportedQuestionFormatError
from pycil.study.schemas import (
    DefinitionDiagnostic,
    RewriteDiagnostic,
    SingleWordDiagnostic,
    UsageDiagnostic,
)
from pycil.vocabulary.enums import HitKind
from pycil.vocabulary.errors import InvalidOutputError, InvalidResourceError
from pycil.vocabulary.models import Definition, Sense, Word
from pycil.vocabulary.schemas import SearchResult
from pycil.vocabulary.text import answer_key
from pycil.vocabulary.types import MeaningSense
from pycil.vocabulary.words import meaning_inventory

logger = get_logger(__name__)


class DecisionLLM(Protocol):
    async def decide[T: BaseModel](self, schema: type[T], context: dict[str, object]) -> T: ...


class SearchProtocol(Protocol):
    async def search(self, query: str, *, limit: int = 20) -> SearchResult: ...


def selected_sense(
    response: object, name: str, senses: Sequence[MeaningSense]
) -> MeaningSense | None:
    choice = str(getattr(response, name))
    if choice == "no_candidate":
        return None
    candidates = {f"sense_{sense['id']}": sense for sense in senses}
    if choice not in candidates:
        raise InvalidOutputError("decision selected an unavailable meaning")
    return candidates[choice]


def unused(
    kind: QuestionType, fmt: ResponseFormat
) -> SingleWordDiagnostic | DefinitionDiagnostic | RewriteDiagnostic | UsageDiagnostic:
    if fmt is ResponseFormat.SINGLE_WORD:
        return SingleWordDiagnostic(task_fit=False, spelling_error=False, sense_id=None)
    if kind is QuestionType.WORD_TO_DEFINITION:
        return DefinitionDiagnostic(sense_id=None, accuracy=None, coverage=None)
    if kind is QuestionType.SENTENCE_REWRITE:
        return RewriteDiagnostic(
            used=False,
            meaning=None,
            form=None,
            construction=None,
            collocation=None,
            appropriacy=None,
            meaning_preservation=None,
        )
    return UsageDiagnostic(
        used=False,
        meaning=None,
        form=None,
        construction=None,
        collocation=None,
        appropriacy=None,
    )


async def grade_answer(
    sessions: async_sessionmaker[AsyncSession],
    search: SearchProtocol,
    decision_llm: DecisionLLM,
    store: InMemoryStore[int, Artifact] | None,
    artifact_id: int,
    kind: QuestionType,
    fmt: ResponseFormat,
    answer: str | None,
    policy: GradingPolicy,
    *,
    allowed_pairs: set[tuple[QuestionType, ResponseFormat]],
) -> SingleWordDiagnostic | DefinitionDiagnostic | RewriteDiagnostic | UsageDiagnostic:
    with observe_operation(
        logger,
        "grading",
        question_artifact_id=artifact_id,
        question_type=kind.value,
        format=fmt.value,
    ):
        artifacts = await get_many(sessions, [artifact_id], store=store)
        if not artifacts:
            raise QuestionArtifactNotFoundError("artifact not found")
        artifact = artifacts[0]
        if (
            QUESTION_ARTIFACT_MAP[kind] != artifact.artifact_type
            or fmt is ResponseFormat.SINGLE_CHOICE
            or (kind, fmt) not in ALLOWED_PAIRS
            or (kind, fmt) not in allowed_pairs
        ):
            raise UnsupportedQuestionFormatError("unsupported exercise format")
        if answer is None:
            return unused(kind, fmt)
        if not answer.strip() or len(answer) > 16000:
            raise InvalidResourceError("invalid learner answer")
        async with sessions() as session:
            facts = (
                await session.execute(
                    select(Word.lemma, Definition.content)
                    .join(Sense, Sense.word_id == Word.id)
                    .join(Definition, Definition.sense_id == Sense.id)
                    .where(Sense.id == artifact.sense_id, Definition.theme_id == artifact.theme_id)
                )
            ).one_or_none()
        if facts is None:
            raise InvalidResourceError("artifact meaning is unavailable")
        lemma: str = str(facts[0])
        meaning: str = str(facts[1])
        if fmt is ResponseFormat.SINGLE_WORD:
            payload_dict = artifact.payload
            correct = (
                cast(str, cast(dict[str, object], payload_dict["correct"])["expression"])
                if kind is QuestionType.CLOZE_TO_WORD
                else lemma
            )
            if answer_key(answer) == answer_key(correct):
                result: (
                    SingleWordDiagnostic
                    | DefinitionDiagnostic
                    | RewriteDiagnostic
                    | UsageDiagnostic
                ) = SingleWordDiagnostic(
                    task_fit=True, spelling_error=False, sense_id=artifact.sense_id
                )
            else:
                context = (
                    meaning
                    if kind is QuestionType.DEFINITION_TO_WORD
                    else cast(str, payload_dict.get("context", lemma))
                )
                result = await _single_word(
                    sessions, search, decision_llm, context, kind, answer, policy
                )
        elif kind is QuestionType.WORD_TO_DEFINITION:
            result = await _definition(sessions, decision_llm, artifact.sense_id, answer)
        else:
            payload_dict = artifact.payload
            source = (
                cast(str, payload_dict["source"]) if kind is QuestionType.SENTENCE_REWRITE else None
            )
            result = await _usage(decision_llm, lemma, meaning, answer, policy, kind, source)
        return result


async def _single_word(
    sessions: async_sessionmaker[AsyncSession],
    search: SearchProtocol,
    decision_llm: DecisionLLM,
    context: str,
    kind: QuestionType,
    answer: str,
    policy: GradingPolicy,
) -> SingleWordDiagnostic:
    response = await decision_llm.decide(
        single_word_model(kind),
        {"question": context, "answer": answer},
    )
    single_word_resp = response
    threshold = policy.decision_threshold
    task_fit = bool(single_word_resp.task_fit >= threshold)
    spelling_error = bool(single_word_resp.spelling_error >= threshold)
    if len(answer.strip()) > 256:
        return SingleWordDiagnostic(task_fit=task_fit, spelling_error=spelling_error, sense_id=None)
    result = await search.search(answer, limit=1)
    if not result.items or result.items[0].kind is not HitKind.WORD:
        return SingleWordDiagnostic(task_fit=task_fit, spelling_error=spelling_error, sense_id=None)
    word_hit = result.items[0]
    meanings = await meaning_inventory(sessions, word_id=word_hit.word_id)
    if not meanings or not meanings["senses"]:
        return SingleWordDiagnostic(task_fit=task_fit, spelling_error=spelling_error, sense_id=None)
    decision_resp = await decision_llm.decide(
        sense_selection_model("matched_sense", meanings),
        {"question": context, "answer": answer},
    )
    selected = selected_sense(decision_resp, "matched_sense", meanings["senses"])
    return SingleWordDiagnostic(
        task_fit=task_fit,
        spelling_error=spelling_error,
        sense_id=selected["id"] if selected else None,
    )


async def _definition(
    sessions: async_sessionmaker[AsyncSession],
    decision_llm: DecisionLLM,
    sense_id: int,
    answer: str,
) -> DefinitionDiagnostic:
    meanings = await meaning_inventory(sessions, sense_id=sense_id)
    if not meanings or not meanings["senses"]:
        raise InvalidResourceError("artifact word has no published meanings")
    decision_resp = await decision_llm.decide(
        sense_selection_model("defined_meaning", meanings),
        {"word": meanings["lemma"], "answer": answer},
    )
    selected = selected_sense(decision_resp, "defined_meaning", meanings["senses"])
    if selected is None:
        return DefinitionDiagnostic(sense_id=None, accuracy=None, coverage=None)
    assessment = await decision_llm.decide(
        DefinitionAssessment,
        {"word": meanings["lemma"], "meaning": selected["definition"], "answer": answer},
    )
    return DefinitionDiagnostic(
        sense_id=selected["id"],
        accuracy=DefinitionAccuracy(assessment.accuracy),
        coverage=DefinitionCoverage(assessment.coverage),
    )


async def _usage(
    decision_llm: DecisionLLM,
    lemma: str,
    meaning: str,
    answer: str,
    policy: GradingPolicy,
    kind: QuestionType,
    source: str | None,
) -> RewriteDiagnostic | UsageDiagnostic:
    threshold = policy.decision_threshold
    use_resp = await decision_llm.decide(
        TargetUseAssessment,
        {"word": lemma, "answer": answer},
    )
    if use_resp.used < threshold:
        diag = unused(kind, ResponseFormat.SHORT_ANSWER)
        assert isinstance(diag, (RewriteDiagnostic, UsageDiagnostic))
        return diag
    context: dict[str, object] = {"word": lemma, "meaning": meaning, "answer": answer}
    if kind is QuestionType.SENTENCE_REWRITE:
        context["source"] = source
        rewrite_assessment = await decision_llm.decide(RewriteAssessment, context)
        return RewriteDiagnostic(
            used=True,
            meaning=UsageMeaning(rewrite_assessment.meaning),
            form=UsageForm(rewrite_assessment.form),
            construction=bool(rewrite_assessment.construction >= threshold),
            collocation=bool(rewrite_assessment.collocation >= threshold),
            appropriacy=bool(rewrite_assessment.appropriacy >= threshold),
            meaning_preservation=MeaningPreservation(rewrite_assessment.meaning_preservation),
        )
    usage_assessment = await decision_llm.decide(UsageAssessment, context)
    return UsageDiagnostic(
        used=True,
        meaning=UsageMeaning(usage_assessment.meaning),
        form=UsageForm(usage_assessment.form),
        construction=bool(usage_assessment.construction >= threshold),
        collocation=bool(usage_assessment.collocation >= threshold),
        appropriacy=bool(usage_assessment.appropriacy >= threshold),
    )
