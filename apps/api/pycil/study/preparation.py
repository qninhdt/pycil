"""Select ready Senses in SQL; allocate banks and retrieve native artifacts once."""

import random
from datetime import UTC, datetime

from lexi_ai import ResponseFormat
from lexi_ai.contract import Question
from lexi_ai.errors import QuestionBankChangedError
from sqlalchemy import DateTime, literal, select, union_all

from pycil.account.models import User
from pycil.account.schemas import effective_learning
from pycil.http import Problem
from pycil.library.access import readable
from pycil.library.senses import member_ids
from pycil.study.models import SenseMemory

randomness = random.SystemRandom()


def bundle(questions, preferences, last_rating, config):
    feasible = {
        kind: [
            fmt for fmt in preferences.formats if fmt in config.learning.pair_levels.get(kind, {})
        ]
        for kind in preferences.question_types
    }
    choices = []
    if ResponseFormat.SINGLE_CHOICE in preferences.formats:
        for question in questions:
            formats = feasible[question.question_type]
            choices.append(
                ResponseFormat.SINGLE_CHOICE
                if ResponseFormat.SINGLE_CHOICE in formats
                else randomness.choice(formats)
            )
        mix = config.learning.format_mix[last_rating.value if last_rating else "NEW"]
        for fmt, cap in (
            (ResponseFormat.SHORT_ANSWER, mix.max_short_answer),
            (ResponseFormat.SINGLE_WORD, mix.max_single_word),
        ):
            eligible = [
                index
                for index, question in enumerate(questions)
                if choices[index] is ResponseFormat.SINGLE_CHOICE
                and fmt in feasible[question.question_type]
            ]
            for index in randomness.sample(eligible, min(cap, len(eligible))):
                choices[index] = fmt
    else:
        choices = [randomness.choice(feasible[q.question_type]) for q in questions]
    result = []
    for question, fmt in zip(questions, choices, strict=True):
        options = [question.correct, *question.distractors]
        randomness.shuffle(options)
        result.append(
            {
                "question": question,
                "format": fmt,
                "level": config.learning.pair_levels[question.question_type][fmt],
                "options": options,
            }
        )
    return result


async def prepare(session, lexicon, user, node_id, config):
    async with session.begin():
        plan = await session.scalar(select(User.plan).where(User.id == user.id))
    if plan is None:
        raise Problem(404, "account_not_found")
    preferences = effective_learning(user.settings, plan, config)
    target = preferences.question_budget // preferences.questions_per_sense
    now = datetime.now(UTC)
    k = preferences.questions_per_sense
    types = [
        kind
        for kind in preferences.question_types
        if any(fmt in config.learning.pair_levels.get(kind, {}) for fmt in preferences.formats)
    ]
    available = select(Question.id).where(
        Question.theme_id.is_(None), Question.question_type.in_(types)
    )
    # Scope, memory and readiness share this snapshot. Native bank retrieval runs
    # later and reports changed content, rather than promising cross-store snapshots.
    async with session.begin():
        await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        node = await readable(session, node_id, user.id, config)
        scope = (
            member_ids(node, user.id, config).cte("preparation_scope").prefix_with("MATERIALIZED")
        )
        memory = SenseMemory
        learned = select(memory.sense_id, memory.last_rating, memory.due_at).where(
            memory.user_id == user.id,
            memory.sense_id.in_(select(scope.c.sense_id)),
            available.where(Question.sense_id == memory.sense_id).offset(k - 1).limit(1).exists(),
        )
        fresh = select(
            scope.c.sense_id,
            literal(None, type_=memory.last_rating.type).label("last_rating"),
            literal(None, type_=DateTime(timezone=True)).label("due_at"),
        ).where(
            ~select(memory.sense_id)
            .where(memory.user_id == user.id, memory.sense_id == scope.c.sense_id)
            .correlate(scope)
            .exists(),
            available.where(Question.sense_id == scope.c.sense_id).offset(k - 1).limit(1).exists(),
        )
        phases = (
            learned.add_columns(literal(0).label("priority"), literal("DUE").label("reason"))
            .where(memory.due_at <= now)
            .order_by(memory.due_at, memory.sense_id)
            .limit(target),
            fresh.add_columns(literal(1).label("priority"), literal("NEW").label("reason"))
            .order_by(scope.c.sense_id)
            .limit(target),
            (
                learned.add_columns(
                    literal(2).label("priority"), literal("NOT_YET_DUE").label("reason")
                )
                .where(memory.due_at > now)
                .order_by(memory.due_at, memory.sense_id)
                .limit(target)
            ),
        )
        candidates = union_all(*phases).subquery("learning_candidates")
        selected = (
            select(candidates)
            .order_by(candidates.c.priority, candidates.c.due_at, candidates.c.sense_id)
            .limit(target)
            .cte("selected_senses")
            .prefix_with("MATERIALIZED")
        )
        rows = (
            await session.execute(
                select(selected).order_by(
                    selected.c.priority, selected.c.due_at, selected.c.sense_id
                )
            )
        ).all()
    selected_senses = {row.sense_id: row for row in rows}
    counts = await lexicon.count_questions_for_senses(list(selected_senses), types)
    requests = []
    for sense_id in selected_senses:
        remaining = {kind: counts.get((sense_id, kind), 0) for kind in types}
        if sum(remaining.values()) < k:
            raise Problem(409, "learning_content_changed")
        allocation = dict.fromkeys(types, 0)
        for _ in range(k):
            kind = randomness.choices(types, weights=[remaining[t] for t in types], k=1)[0]
            allocation[kind] += 1
            remaining[kind] -= 1
        requests.extend((sense_id, kind, count) for kind, count in allocation.items() if count)
    try:
        questions = await lexicon.retrieve_questions(requests) if requests else []
    except QuestionBankChangedError:
        raise Problem(409, "learning_content_changed") from None
    senses = {sense.id: sense for sense in await lexicon.get_senses(list(selected_senses))}
    if len(senses) != len(selected_senses):
        raise Problem(409, "learning_content_changed")
    banks = {sense_id: [] for sense_id in selected_senses}
    for question in questions:
        banks[question.sense_id].append(question)
    result = [
        {
            "sense": senses[sense_id],
            "reason": row.reason,
            "questions": bundle(banks[sense_id], preferences, row.last_rating, config),
        }
        for sense_id, row in selected_senses.items()
    ]
    return {
        "requested_sense_count": target,
        "actual_sense_count": len(result),
        "actual_question_count": len(result) * preferences.questions_per_sense,
        "preferences": preferences,
        "bundles": result,
    }
