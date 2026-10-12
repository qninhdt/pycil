"""Select Senses in SQL, plan public pairs, then retrieve or fill artifact banks."""

import random
from collections import Counter, defaultdict
from datetime import UTC, datetime

from lexi_ai import QUESTION_ARTIFACT_MAP
from lexi_ai.errors import LexiconError, QuestionArtifactBankChangedError
from sqlalchemy import DateTime, Float, literal, select

from pycil.account.models import User
from pycil.account.schemas import effective_learning
from pycil.http import Problem
from pycil.library.access import readable
from pycil.library.senses import member_ids
from pycil.study.models import UserSense
from pycil.study.questions import build_question

randomness = random.SystemRandom()


def plan_pairs(elo, preferences, config, k):
    level = config.learning.mastery.level(elo)
    pairs = [
        (kind, fmt, config.learning.pair_levels[kind][fmt])
        for kind in preferences.question_types
        for fmt in preferences.formats
        if fmt in config.learning.pair_levels.get(kind, {})
    ]
    if not pairs:
        raise Problem(422, "infeasible_learning_preferences")
    levels = sorted({entry[2] for entry in pairs if entry[2] <= level})
    if not levels:
        levels = [min(entry[2] for entry in pairs)]
    result = []
    for _ in range(k):
        selected = randomness.choices(
            levels, weights=[2 ** (candidate_level - level) for candidate_level in levels], k=1
        )[0]
        kind, fmt, _ = randomness.choice([entry for entry in pairs if entry[2] == selected])
        result.append((kind, fmt))
    return result


async def prepare(
    session,
    lexicon,
    user,
    node_id,
    config,
    *,
    selection="AUTO",
    max_sense_count=None,
    questions_per_sense=None,
):
    async with session.begin():
        current = await session.scalar(
            select(User).where(User.id == user.id).execution_options(populate_existing=True)
        )
    if current is None:
        raise Problem(404, "account_not_found")
    preferences = effective_learning(current.settings, current.plan, config)
    target = max_sense_count if max_sense_count is not None else preferences.max_sense_count
    k = questions_per_sense if questions_per_sense is not None else preferences.questions_per_sense
    preferences = preferences.model_copy(
        update={"max_sense_count": target, "questions_per_sense": k}
    )
    if selection not in {"AUTO", "NEW", "DUE"}:
        raise Problem(422, "invalid_preparation")
    try:
        config.learning.validate_preferences(preferences)
    except ValueError as exc:
        raise Problem(422, "invalid_preparation") from exc
    now = datetime.now(UTC)
    async with session.begin():
        await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        node = await readable(session, node_id, user.id, config)
        scope = (await member_ids(session, node, user.id, config)).cte("preparation_scope")
        learned = select(UserSense.sense_id, UserSense.elo, UserSense.due_at).where(
            UserSense.user_id == user.id, UserSense.sense_id.in_(select(scope.c.sense_id))
        )
        fresh = select(
            scope.c.sense_id,
            literal(config.learning.mastery.initial_elo, type_=Float).label("elo"),
            literal(None, type_=DateTime(timezone=True)).label("due_at"),
        ).where(
            ~select(UserSense.sense_id)
            .where(UserSense.user_id == user.id, UserSense.sense_id == scope.c.sense_id)
            .correlate(scope)
            .exists()
        )
        phases = (
            learned.add_columns(literal("DUE").label("reason"))
            .where(UserSense.due_at <= now)
            .order_by(UserSense.due_at, UserSense.sense_id),
            fresh.add_columns(literal("NEW").label("reason")).order_by(scope.c.sense_id),
            learned.add_columns(literal("NOT_YET_DUE").label("reason"))
            .where(UserSense.due_at > now)
            .order_by(UserSense.due_at, UserSense.sense_id),
        )
        rows = []
        for index in {"AUTO": (0, 1, 2), "DUE": (0,), "NEW": (1,)}[selection]:
            if len(rows) == target:
                break
            rows.extend((await session.execute(phases[index].limit(target - len(rows)))).all())
    plans = {row.sense_id: plan_pairs(row.elo, preferences, config, k) for row in rows}
    demand = Counter((sense_id, kind) for sense_id, pairs in plans.items() for kind, _ in pairs)
    try:
        artifacts = (
            await lexicon.retrieve_question_artifacts(
                [(sense_id, kind, count) for (sense_id, kind), count in demand.items()],
                generate=True,
                generation_batch_size=config.generation.question_artifact_batch_size,
                correct_count=config.generation.correct_count,
                distractor_count=config.generation.distractor_count,
            )
            if demand
            else []
        )
    except QuestionArtifactBankChangedError:
        raise Problem(409, "learning_content_changed") from None
    except LexiconError:
        raise Problem(503, "question_generation_unavailable") from None
    senses = {s.id: s for s in await lexicon.get_senses(list(plans))}
    facts = {s["sense_id"]: s for s in await lexicon.get_sense_previews(list(plans))}
    if len(senses) != len(plans) or len(facts) != len(plans):
        raise Problem(409, "learning_content_changed")
    banks = defaultdict(list)
    for artifact in artifacts:
        banks[artifact.sense_id, artifact.artifact_type].append(artifact)
    bundles = []
    for row in rows:
        questions = []
        for kind, fmt in plans[row.sense_id]:
            bank = banks[row.sense_id, QUESTION_ARTIFACT_MAP[kind]]
            if not bank:
                raise Problem(409, "learning_content_changed")
            questions.append(
                build_question(
                    randomness.choice(bank),
                    kind,
                    fmt,
                    senses[row.sense_id],
                    facts[row.sense_id]["lemma"],
                    config,
                )
            )
        bundles.append(dict(sense=senses[row.sense_id], reason=row.reason, questions=questions))
    return dict(
        node_id=node_id,
        selection=selection,
        max_sense_count=target,
        actual_sense_count=len(bundles),
        actual_question_count=len(bundles) * k,
        preferences=preferences,
        bundles=bundles,
    )
