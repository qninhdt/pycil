"""Atomic diagnostic tracking, grouped Sense updates and immutable receipts."""

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from lexi_ai import QUESTION_ARTIFACT_MAP, QuestionType, ResponseFormat
from lexi_ai.contract import QuestionArtifact, Sense
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from pycil.account.lifecycle import require_user
from pycil.account.models import User
from pycil.account.schemas import preferences
from pycil.database import transaction_lock
from pycil.http import Problem
from pycil.study.evidence import evidence, update_elo
from pycil.study.fsrs import next_state
from pycil.study.models import DailyActivity, ReviewReceipt, UserSense
from pycil.study.schemas import BatchResult


def request_hash(data):
    encoded = json.dumps(
        data.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


async def review(session, user_id, data, event_key, config):
    if len(data.results) > config.learning.limits.max_review_batch:
        raise Problem(422, "review_batch_too_large")
    digest = request_hash(data)
    async with session.begin():
        # Serialize first inserts and overlapping batches without a per-Sense lock query.
        await transaction_lock(session, f"learning:{user_id}")
        await require_user(session, user_id)
        previous = await session.get(ReviewReceipt, (user_id, event_key))
        if previous is not None:
            if previous.request_hash != digest:
                raise Problem(409, "review_batch_conflict")
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
        groups, tracked = defaultdict(list), []
        now = datetime.now(UTC)
        policy = config.learning.mastery
        for item in data.results:
            artifact = artifacts[item.question_artifact_id]
            formats = config.learning.pair_levels.get(item.question_type, {})
            if (
                QUESTION_ARTIFACT_MAP[item.question_type] != artifact.artifact_type
                or item.format not in formats
            ):
                raise Problem(422, "unsupported_question_format")
            if item.answered_at > now:
                raise Problem(422, "invalid_answered_at")
            sense_id, recall, performance = evidence(item, artifact.sense_id)
            difficulty = policy.opponent_elo[formats[item.format] - 1]
            record = item.model_dump(mode="json") | dict(
                evaluated_sense_id=sense_id,
                recall=recall,
                performance=performance,
                opponent_elo=difficulty,
                policy_version=policy.policy_version,
            )
            tracked.append(record)
            groups[sense_id].append((item, recall, performance, difficulty))
        sense_ids = (
            set(groups)
            | {a.sense_id for a in artifacts.values()}
            | {
                item.diagnostics.sense_id
                for item in data.results
                if hasattr(item.diagnostics, "sense_id") and item.diagnostics.sense_id is not None
            }
        )
        words = dict(
            (
                await session.execute(
                    select(Sense.id, Sense.word_id).where(Sense.id.in_(sense_ids))
                )
            ).all()
        )
        if set(words) != sense_ids:
            raise Problem(422, "sense_not_found")
        for item in data.results:
            if (
                item.question_type == QuestionType.WORD_TO_DEFINITION
                and item.format == ResponseFormat.SHORT_ANSWER
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
        results, states = [], []
        for sense_id, group in groups.items():
            memory = memories.get(sense_id)
            review_time = max(item.answered_at for item, _, _, _ in group)
            applied = memory is None or review_time >= memory.last_exposure_at
            if applied:
                elo = update_elo(
                    memory.elo if memory else policy.initial_elo,
                    [(p, d) for _, _, p, d in group],
                    memory.last_exposure_at if memory else None,
                    review_time,
                    policy,
                )
                stability, difficulty, due = next_state(
                    memory, [r for _, r, _, _ in group], review_time, config
                )
                state = dict(
                    user_id=user_id,
                    sense_id=sense_id,
                    elo=elo,
                    stability=stability,
                    difficulty=difficulty,
                    last_exposure_at=review_time,
                    due_at=due,
                    review_count=(memory.review_count if memory else 0) + 1,
                    lapse_count=(memory.lapse_count if memory else 0)
                    + int(memory is not None and any(r == 0 for _, r, _, _ in group)),
                    created_at=memory.created_at if memory else now,
                    updated_at=now,
                )
                states.append(state)
            else:
                state = {
                    field: getattr(memory, field)
                    for field in ("elo", "stability", "difficulty", "last_exposure_at", "due_at")
                }
            results.append(
                dict(
                    sense_id=sense_id,
                    applied=applied,
                    elo=state["elo"],
                    level=policy.level(state["elo"]),
                    stability=state["stability"],
                    difficulty=state["difficulty"],
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
                        field: getattr(statement.excluded, field)
                        for field in states[0]
                        if field not in {"user_id", "sense_id", "created_at"}
                    },
                )
            )
        result = BatchResult(
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
        statement = insert(DailyActivity).values(
            user_id=user_id,
            day=day,
            applied_events=len(states),
            practice_events=len(groups) - len(states),
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[DailyActivity.user_id, DailyActivity.day],
                set_={
                    "applied_events": DailyActivity.applied_events
                    + statement.excluded.applied_events,
                    "practice_events": DailyActivity.practice_events
                    + statement.excluded.practice_events,
                },
            )
        )
        await session.flush()
        return result
