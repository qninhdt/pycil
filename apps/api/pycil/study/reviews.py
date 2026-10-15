"""Atomic diagnostic tracking, grouped Sense updates and immutable receipts."""

import hashlib
from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import orjson
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.lifecycle import require_user
from pycil.account.models import User
from pycil.account.settings import preferences
from pycil.app.config import AppConfig
from pycil.app.http import Problem
from pycil.infrastructure.database import transaction_lock
from pycil.infrastructure.observability import get_logger
from pycil.study.enums import QUESTION_ARTIFACT_MAP, QuestionType, ResponseFormat
from pycil.study.evidence import evidence, update_elo
from pycil.study.fsrs import next_state
from pycil.study.models import DailyActivity, QuestionArtifact, ReviewReceipt, UserSense
from pycil.study.schemas import (
    BatchResult,
    DefinitionDiagnostic,
    Review,
    ReviewBatch,
    ReviewResult,
    SingleWordDiagnostic,
    TrackedEvidence,
)
from pycil.study.types import UserSenseState
from pycil.vocabulary.models import Sense

logger = get_logger(__name__)


def request_hash(data: ReviewBatch) -> str:
    encoded = orjson.dumps(data.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(encoded).hexdigest()


async def review(
    session: AsyncSession,
    user_id: UUID,
    data: ReviewBatch,
    event_key: UUID,
    config: AppConfig,
) -> dict[str, object]:
    if len(data.results) > config.product.study.limits.max_review_batch:
        raise Problem(422, "review_batch_too_large")
    digest = request_hash(data)
    async with session.begin():
        # Serialize first inserts and overlapping batches without a per-Sense lock query.
        await transaction_lock(session, f"learning:{user_id}")
        await require_user(session, user_id)
        previous = await session.get(ReviewReceipt, (user_id, event_key))
        if previous is not None:
            if previous.request_hash != digest:
                logger.warning(
                    "review_batch_conflict",
                    user_id=str(user_id),
                    event_key=str(event_key),
                )
                raise Problem(409, "review_batch_conflict")
            logger.info(
                "review_batch_replayed",
                user_id=str(user_id),
                event_key=str(event_key),
            )
            return previous.result
        ids = {r.question_artifact_id for r in data.results}
        artifacts = {
            a.id: a
            for a in (
                await session.scalars(select(QuestionArtifact).where(QuestionArtifact.id.in_(ids)))
            ).all()
        }
        if len(artifacts) != len(ids):
            raise Problem(422, "question_artifact_not_found")
        groups: defaultdict[int, list[tuple[Review, float | None, float | None, float]]] = (
            defaultdict(list)
        )
        tracked: list[TrackedEvidence] = []
        now = datetime.now(UTC)
        policy = config.product.study.mastery
        for item in data.results:
            artifact = artifacts[item.question_artifact_id]
            formats = config.product.study.pair_levels.get(item.question_type, {})
            if (
                QUESTION_ARTIFACT_MAP[item.question_type] != artifact.artifact_type
                or item.format not in formats
            ):
                raise Problem(422, "unsupported_question_format")
            if item.answered_at > now:
                raise Problem(422, "invalid_answered_at")
            sense_id, recall, performance = evidence(item, artifact.sense_id)
            difficulty = float(policy.opponent_elo[formats[item.format] - 1])
            record = item.model_dump(mode="json") | dict(
                evaluated_sense_id=sense_id,
                recall=recall,
                performance=performance,
                opponent_elo=difficulty,
                policy_version=policy.policy_version,
            )
            tracked.append(TrackedEvidence.model_validate(record))
            groups[sense_id].append((item, recall, performance, difficulty))
        sense_ids = (
            set(groups)
            | {a.sense_id for a in artifacts.values()}
            | {
                item.diagnostics.sense_id
                for item in data.results
                if isinstance(item.diagnostics, (SingleWordDiagnostic, DefinitionDiagnostic))
                and item.diagnostics.sense_id is not None
            }
        )
        words: dict[int, int] = {
            r[0]: r[1]
            for r in (
                await session.execute(
                    select(Sense.id, Sense.word_id).where(Sense.id.in_(sense_ids))
                )
            ).all()
        }
        if set(words) != sense_ids:
            raise Problem(422, "sense_not_found")
        for item in data.results:
            if (
                item.question_type == QuestionType.WORD_TO_DEFINITION
                and item.format == ResponseFormat.SHORT_ANSWER
                and isinstance(item.diagnostics, DefinitionDiagnostic)
                and item.diagnostics.sense_id is not None
            ):
                target = artifacts[item.question_artifact_id].sense_id
                if words[item.diagnostics.sense_id] != words[target]:
                    raise Problem(422, "invalid_definition_sense")
        memories = {
            m.sense_id: m
            for m in (
                await session.scalars(
                    select(UserSense)
                    .where(UserSense.user_id == user_id, UserSense.sense_id.in_(groups))
                    .order_by(UserSense.sense_id)
                    .with_for_update()
                )
            ).all()
        }
        saved = await session.scalar(select(User.settings).where(User.id == user_id))
        day = now.astimezone(ZoneInfo(preferences(saved, config).timezone)).date()
        results: list[ReviewResult] = []
        states: list[UserSenseState] = []
        for sense_id, group in groups.items():
            memory = memories.get(sense_id)
            review_time = max(item.answered_at for item, _, _, _ in group)
            applied = memory is None or review_time >= memory.last_exposure_at
            if applied:
                old_elo = memory.elo if memory else policy.initial_elo
                elo = update_elo(
                    old_elo,
                    [(p, d) for _, _, p, d in group],
                    memory.last_exposure_at if memory else None,
                    review_time,
                    policy,
                )
                logger.info(
                    "study_elo_updated",
                    user_id=str(user_id),
                    sense_id=sense_id,
                    old_elo=old_elo,
                    new_elo=elo,
                )
                stability, difficulty, due = next_state(
                    memory, [r for _, r, _, _ in group], review_time, config
                )
                logger.info(
                    "study_fsrs_transitioned",
                    user_id=str(user_id),
                    sense_id=sense_id,
                    new_stability=round(stability, 4),
                    new_difficulty=round(difficulty, 4),
                    due_at=due.isoformat(),
                )
                state: UserSenseState = {
                    "user_id": user_id,
                    "sense_id": sense_id,
                    "elo": elo,
                    "stability": stability,
                    "difficulty": difficulty,
                    "last_exposure_at": review_time,
                    "due_at": due,
                    "review_count": (memory.review_count if memory else 0) + 1,
                    "lapse_count": (memory.lapse_count if memory else 0)
                    + int(memory is not None and any(r == 0 for _, r, _, _ in group)),
                    "created_at": memory.created_at if memory else now,
                    "updated_at": now,
                }
                states.append(state)
            else:
                assert memory is not None
                state = {
                    "elo": memory.elo,
                    "stability": memory.stability,
                    "difficulty": memory.difficulty,
                    "last_exposure_at": memory.last_exposure_at,
                    "due_at": memory.due_at,
                }
            elo_val = float(state["elo"])
            results.append(
                ReviewResult(
                    sense_id=sense_id,
                    applied=applied,
                    elo=elo_val,
                    level=policy.level(elo_val),
                    stability=float(state["stability"]),
                    difficulty=float(state["difficulty"]),
                    last_exposure_at=state["last_exposure_at"],
                    due_after=state["due_at"],
                )
            )
        if states:
            statement = insert(UserSense).values(states)
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[UserSense.user_id, UserSense.sense_id],
                    set_={
                        "elo": statement.excluded.elo,
                        "stability": statement.excluded.stability,
                        "difficulty": statement.excluded.difficulty,
                        "last_exposure_at": statement.excluded.last_exposure_at,
                        "due_at": statement.excluded.due_at,
                        "review_count": statement.excluded.review_count,
                        "lapse_count": statement.excluded.lapse_count,
                        "updated_at": statement.excluded.updated_at,
                    },
                )
            )
        result: dict[str, object] = BatchResult(
            accepted_at=now, activity_day=day, results=results, evidence=tracked
        ).model_dump(mode="json")
        session.add(
            ReviewReceipt(
                user_id=user_id,
                event_key=event_key,
                request_hash=digest,
                accepted_at=now,
                activity_day=day,
                result=result,
            )
        )
        act_stmt = insert(DailyActivity).values(
            user_id=user_id,
            day=day,
            applied_events=len(states),
            practice_events=len(groups) - len(states),
        )
        await session.execute(
            act_stmt.on_conflict_do_update(
                index_elements=[DailyActivity.user_id, DailyActivity.day],
                set_={
                    "applied_events": DailyActivity.applied_events
                    + act_stmt.excluded.applied_events,
                    "practice_events": DailyActivity.practice_events
                    + act_stmt.excluded.practice_events,
                },
            )
        )
        await session.flush()
        logger.info(
            "review_batch_completed",
            user_id=str(user_id),
            event_key=str(event_key),
            total_reviews=len(data.results),
            applied_count=len(states),
        )
        return result
