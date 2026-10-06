from datetime import UTC, datetime, timedelta

from lexi_ai import Sense
from sqlalchemy import and_, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by

from pycil.account.schemas import preferences
from pycil.http import Problem
from pycil.library.access import readable
from pycil.library.scope import scope_ids
from pycil.library.senses import member_ids
from pycil.study.fsrs import mastery
from pycil.study.models import ReviewLog, SenseMemory


def json_rows(query, *ordering):
    rows = query.subquery()
    value = func.to_jsonb(rows.table_valued())
    if ordering:
        value = aggregate_order_by(value, *(rows.c[key] for key in ordering))
    return select(func.coalesce(func.jsonb_agg(value), literal([], type_=JSONB))).scalar_subquery()


async def progress(session, user, config, node_id=None):
    now = datetime.now(UTC)
    if node_id:
        node = await readable(session, node_id, user.id, config)
        scope = await member_ids(session, node, user.id, config)
    else:
        scope = await scope_ids(session, None, user.id, config)
    scope = scope.cte("progress_scope").prefix_with("MATERIALIZED")
    memory = SenseMemory
    scoped = (
        select(
            scope.c.sense_id,
            memory.stability,
            memory.due_at,
            Sense.cefr_level,
        )
        .outerjoin(memory, and_(memory.sense_id == scope.c.sense_id, memory.user_id == user.id))
        .join(Sense, Sense.id == scope.c.sense_id)
        .cte("scoped_memory")
        .prefix_with("MATERIALIZED")
    )
    summary = (
        select(
            func.jsonb_build_object(
                "total",
                func.count(),
                "learned",
                func.count(scoped.c.stability),
                "due",
                func.count().filter(scoped.c.due_at <= now),
            )
        )
        .select_from(scoped)
        .scalar_subquery()
    )
    timezone = preferences(user.settings, config).timezone
    activity = json_rows(
        select(
            func.date(func.timezone(timezone, ReviewLog.accepted_at)).label("day"),
            func.count().filter(ReviewLog.applied).label("applied_reviews"),
            func.count().filter(~ReviewLog.applied).label("practice_events"),
        )
        .join(scope, scope.c.sense_id == ReviewLog.sense_id)
        .where(
            ReviewLog.user_id == user.id,
            ReviewLog.accepted_at >= now - timedelta(days=config.learning.limits.max_history_days),
        )
        .group_by("day"),
        "day",
    )
    forecast = json_rows(
        select(
            func.date(func.timezone(timezone, scoped.c.due_at)).label("day"),
            func.count().label("count"),
        )
        .where(
            scoped.c.due_at.between(now, now + timedelta(days=config.learning.limits.forecast_days))
        )
        .group_by("day"),
        "day",
    )
    # Drive the top-N from user memory, allowing the stability index to serve
    # global progress and a semi-join to constrain folder/deck progress.
    weakest = json_rows(
        select(memory.sense_id, memory.stability)
        .where(memory.user_id == user.id, memory.sense_id.in_(select(scope.c.sense_id)))
        .order_by(memory.stability, memory.sense_id)
        .limit(config.learning.limits.weakest_senses_limit),
        "stability",
        "sense_id",
    )
    cefr = json_rows(
        select(scoped.c.cefr_level, func.count().label("count")).group_by(scoped.c.cefr_level)
    )
    data = dict(
        (
            await session.execute(
                select(
                    summary.label("summary"),
                    activity.label("activity"),
                    forecast.label("forecast"),
                    weakest.label("weakest_senses"),
                    cefr.label("cefr_distribution"),
                )
            )
        )
        .mappings()
        .one()
    )
    data["weakest_senses"] = [
        {"sense_id": row["sense_id"], "mastery": mastery(row["stability"], config)}
        for row in data["weakest_senses"]
    ]
    return data


async def history(session, user, config, days=30, after=None):
    if not 1 <= days <= config.learning.limits.max_history_days:
        raise Problem(422, "invalid_history_window")
    query = select(ReviewLog).where(
        ReviewLog.user_id == user.id,
        ReviewLog.accepted_at >= datetime.now(UTC) - timedelta(days=days),
    )
    if after:
        from sqlalchemy import tuple_

        cursor = await session.get(ReviewLog, (user.id, after))
        if cursor is None:
            raise Problem(422, "invalid_cursor")
        query = query.where(
            tuple_(ReviewLog.accepted_at, ReviewLog.event_key)
            < tuple_(cursor.accepted_at, cursor.event_key)
        )
    rows = (
        await session.scalars(
            query.order_by(ReviewLog.accepted_at.desc(), ReviewLog.event_key.desc()).limit(
                config.learning.limits.history_page_size + 1
            )
        )
    ).all()
    from pycil.account.lifecycle import row_data

    page = rows[: config.learning.limits.history_page_size]
    return {
        "events": [row_data(row) for row in page],
        "next_after": page[-1].event_key if len(rows) > len(page) else None,
        "applied_count": await session.scalar(
            select(func.count()).select_from(query.where(ReviewLog.applied).subquery())
        ),
    }
