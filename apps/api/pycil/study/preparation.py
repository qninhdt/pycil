"""Select Senses in SQL, plan public pairs, then retrieve or fill artifact banks."""

import random
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from openai import APIError
from sqlalchemy import DateTime, Float, literal, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.account.config import PlanPolicy
from pycil.account.models import User
from pycil.account.plans import Feature, Plan
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.infrastructure.llm import StructuredLLMProtocol
from pycil.infrastructure.retry import ProviderOutputError
from pycil.library.access import readable
from pycil.library.config import LibraryConfig
from pycil.library.senses import member_ids
from pycil.observability import get_logger
from pycil.study.artifacts.generation import retrieve_artifacts
from pycil.study.artifacts.schemas import Artifact
from pycil.study.config import LearningPreferences, StudyConfig, effective_learning
from pycil.study.enums import (
    QUESTION_ARTIFACT_MAP,
    LearningState,
    QuestionArtifactType,
    QuestionType,
    ResponseFormat,
    Selection,
)
from pycil.study.errors import QuestionArtifactBankChangedError
from pycil.study.models import UserSense
from pycil.study.questions import build_question
from pycil.study.schemas import PreparedQuestion
from pycil.study.types import PreparationBundleDict
from pycil.utils.errors import Conflict, Forbidden, InvalidInput, NotFound, Unavailable
from pycil.vocabulary.errors import VocabularyError
from pycil.vocabulary.schemas import Sense
from pycil.vocabulary.types import SenseSummaryDict
from pycil.vocabulary.words import get_sense_previews, get_senses

logger = get_logger(__name__)
randomness = random.SystemRandom()


@dataclass(frozen=True)
class PlannedRow:
    sense_id: int
    elo: float
    due_at: datetime | None
    reason: LearningState


def plan_pairs(
    elo: float, preferences: LearningPreferences, policy: StudyConfig, k: int
) -> list[tuple[QuestionType, ResponseFormat]]:
    level = policy.mastery.level(elo)
    pairs = [
        (kind, fmt, policy.pair_levels[kind][fmt])
        for kind in preferences.question_types
        for fmt in preferences.formats
        if fmt in policy.pair_levels.get(kind, {})
    ]
    if not pairs:
        raise InvalidInput("infeasible_learning_preferences")
    levels = sorted({entry[2] for entry in pairs if entry[2] <= level})
    if not levels:
        levels = [min(entry[2] for entry in pairs)]
    result: list[tuple[QuestionType, ResponseFormat]] = []
    for _ in range(k):
        selected = randomness.choices(
            levels, weights=[2 ** (candidate_level - level) for candidate_level in levels], k=1
        )[0]
        kind, fmt, _ = randomness.choice([entry for entry in pairs if entry[2] == selected])
        result.append((kind, fmt))
    return result


async def normalize_preparation(
    session: AsyncSession,
    user: UUID,
    policy: StudyConfig,
    *,
    selection: Selection = Selection.AUTO,
    max_sense_count: int | None = None,
    questions_per_sense: int | None = None,
    preferences: LearningPreferences | None = None,
    plans: Mapping[Plan, PlanPolicy],
) -> LearningPreferences:
    async with session.begin():
        current = await session.scalar(
            select(User).where(User.id == user).execution_options(populate_existing=True)
        )
    if current is None:
        raise NotFound("account_not_found")
    if preferences is not None:
        current_preferences = effective_learning(
            {"learning": preferences.model_dump(mode="json")},
            policy,
            advanced=Feature.ADVANCED_GRADING in plans[current.plan].features,
        )
        if current_preferences != preferences:
            raise Forbidden("advanced_grading_not_available")
    else:
        preferences = effective_learning(
            current.settings,
            policy,
            advanced=Feature.ADVANCED_GRADING in plans[current.plan].features,
        )
    target = max_sense_count if max_sense_count is not None else preferences.max_sense_count
    k = questions_per_sense if questions_per_sense is not None else preferences.questions_per_sense
    preferences = preferences.model_copy(
        update={"max_sense_count": target, "questions_per_sense": k}
    )
    if selection not in {Selection.AUTO, Selection.NEW, Selection.DUE}:
        raise InvalidInput("invalid_preparation")
    try:
        policy.validate_preferences(preferences)
    except ValueError as exc:
        raise InvalidInput("invalid_preparation") from exc
    return preferences


async def prepare(
    session: AsyncSession,
    sessions: async_sessionmaker[AsyncSession],
    structured_llm: StructuredLLMProtocol,
    artifact_store: InMemoryStore[int, Artifact] | None,
    user: UUID,
    node_id: UUID,
    policy: StudyConfig,
    *,
    sense_store: InMemoryStore[int, Sense] | None = None,
    preferences: LearningPreferences,
    selection: Selection = Selection.AUTO,
    library_config: LibraryConfig,
    generation_batch_size: int,
) -> dict[str, object]:
    target, k = preferences.max_sense_count, preferences.questions_per_sense
    logger.info(
        "study_preparation_started",
        user_id=str(user),
        node_id=str(node_id),
        selection=selection,
        max_sense_count=target,
    )
    now = datetime.now(UTC)
    async with session.begin():
        await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        node = await readable(session, node_id, user)
        scope = (
            await member_ids(session, node, user, library_config)
        ).cte("preparation_scope")
        learned = select(UserSense.sense_id, UserSense.elo, UserSense.due_at).where(
            UserSense.user_id == user, UserSense.sense_id.in_(select(scope.c.sense_id))
        )
        fresh = select(
            scope.c.sense_id,
            literal(policy.mastery.initial_elo, type_=Float()).label("elo"),
            literal(None, type_=DateTime(timezone=True)).label("due_at"),
        ).where(
            ~select(UserSense.sense_id)
            .where(UserSense.user_id == user, UserSense.sense_id == scope.c.sense_id)
            .correlate(scope)
            .exists()
        )
        phases = (
            learned.add_columns(literal(LearningState.DUE).label("reason"))
            .where(UserSense.due_at <= now)
            .order_by(UserSense.due_at, UserSense.sense_id),
            fresh.add_columns(literal(LearningState.NEW).label("reason")).order_by(
                scope.c.sense_id
            ),
            learned.add_columns(literal(LearningState.NOT_YET_DUE).label("reason"))
            .where(UserSense.due_at > now)
            .order_by(UserSense.due_at, UserSense.sense_id),
        )
        rows: list[PlannedRow] = []
        for index in {Selection.AUTO: (0, 1, 2), Selection.DUE: (0,), Selection.NEW: (1,)}[
            selection
        ]:
            if len(rows) == target:
                break
            executed = (await session.execute(phases[index].limit(target - len(rows)))).all()
            for r in executed:
                rows.append(
                    PlannedRow(
                        sense_id=int(r[0]),
                        elo=float(r[1]),
                        due_at=cast(datetime | None, r[2]),
                        reason=LearningState(str(r[3])),
                    )
                )
    plans = {row.sense_id: plan_pairs(row.elo, preferences, policy, k) for row in rows}
    demand = Counter((sense_id, kind) for sense_id, pairs in plans.items() for kind, _ in pairs)
    try:
        artifacts = (
            await retrieve_artifacts(
                sessions,
                structured_llm,
                artifact_store,
                [(sense_id, kind, count) for (sense_id, kind), count in demand.items()],
                generation_batch_size=generation_batch_size,
                correct_count=policy.artifacts.correct_count,
                distractor_count=policy.artifacts.distractor_count,
            )
            if demand
            else []
        )
    except QuestionArtifactBankChangedError as exc:
        logger.warning(
            "study_artifact_retrieval_failed",
            user_id=str(user),
            node_id=str(node_id),
            error_type=type(exc).__name__,
        )
        raise Conflict("learning_content_changed") from None
    except (VocabularyError, APIError, ProviderOutputError) as exc:
        logger.warning(
            "study_artifact_retrieval_failed",
            user_id=str(user),
            node_id=str(node_id),
            error_type=type(exc).__name__,
        )
        raise Unavailable("question_generation_unavailable") from None
    senses: dict[int, Sense] = {
        s.id: s for s in await get_senses(sessions, list(plans), store=sense_store)
    }
    facts: dict[int, SenseSummaryDict] = {
        s["sense_id"]: s for s in await get_sense_previews(sessions, list(plans))
    }
    if len(senses) != len(plans) or len(facts) != len(plans):
        raise Conflict("learning_content_changed")
    banks: dict[tuple[int, QuestionArtifactType], list[Artifact]] = defaultdict(list)
    for artifact in artifacts:
        banks[artifact.sense_id, artifact.artifact_type].append(artifact)
    bundles: list[PreparationBundleDict] = []
    for row in rows:
        questions: list[PreparedQuestion] = []
        for kind, fmt in plans[row.sense_id]:
            bank = banks[row.sense_id, QUESTION_ARTIFACT_MAP[kind]]
            if not bank:
                raise Conflict("learning_content_changed")
            lemma_val = facts[row.sense_id]["lemma"]
            questions.append(
                build_question(
                    randomness.choice(bank),
                    kind,
                    fmt,
                    senses[row.sense_id],
                    lemma_val,
                    policy,
                )
            )
        bundles.append(
            {"sense": senses[row.sense_id], "reason": row.reason, "questions": questions}
        )
    logger.info(
        "study_preparation_completed",
        user_id=str(user),
        node_id=str(node_id),
        selection=selection,
        sense_count=len(bundles),
        question_count=len(bundles) * k,
    )
    return dict(
        node_id=node_id,
        selection=selection,
        max_sense_count=target,
        actual_sense_count=len(bundles),
        actual_question_count=len(bundles) * k,
        preferences=preferences,
        bundles=bundles,
    )
