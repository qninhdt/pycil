"""Exact bounded scope summaries and independent durable activity/schedule reads."""

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, Uuid, and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.auth import Actor
from pycil.account.models import User
from pycil.account.settings import preferences
from pycil.app.config import ProductConfig
from pycil.app.http import Problem
from pycil.library.models import DeckSense, NodeType
from pycil.library.scope import Scope, ScopeBudget, bounded, resolve_scopes
from pycil.study.models import DailyActivity, UserSense


def scope_mapping(
    scopes: Iterable[Scope],
    budget: ScopeBudget,
    config: ProductConfig,
) -> tuple[dict[UUID, int], list[tuple[int, UUID]]]:
    groups: dict[frozenset[UUID], int] = {}
    group_ids: dict[UUID, int] = {}
    mapping: list[tuple[int, UUID]] = []
    for scope in scopes:
        key = frozenset(scope.decks)
        if key not in groups:
            group = len(groups)
            groups[key] = group
            mapping.extend((group, deck) for deck in key)
        group_ids[scope.root.id] = groups[key]
    logical_work = sum(sum(budget.membership_counts.get(deck, 0) for deck in key) for key in groups)
    if logical_work > config.projections.max_summary_memberships:
        raise Problem(422, "scope_too_large")
    return group_ids, mapping


async def summaries(
    session: AsyncSession,
    viewer_id: UUID | None,
    config: ProductConfig,
    node_ids: Sequence[UUID | None],
    *,
    budget: ScopeBudget | None = None,
) -> list[dict[str, Any]]:
    if (
        not node_ids
        or len(node_ids) > config.learning.limits.max_summary_nodes
        or len(set(node_ids)) != len(node_ids)
    ):
        raise Problem(422, "invalid_summary_batch")
    budget = budget or ScopeBudget(viewer_id)
    async with bounded(session, config, budget):
        scopes = await resolve_scopes(session, node_ids, viewer_id, config, budget=budget)
        now = datetime.now(UTC)
        group_ids, mapping = scope_mapping(scopes.values(), budget, config)
        aggregated: dict[int, dict[str, Any]] = {}
        if mapping:
            # Arrays avoid PostgreSQL's parameter count limit for a large bounded deck mapping.
            mapped = (
                text(
                    "SELECT unnest(CAST(:groups AS integer[])) AS grp, "
                    "unnest(CAST(:decks AS uuid[])) AS deck_id"
                )
                .bindparams(groups=[g for g, _ in mapping], decks=[d for _, d in mapping])
                .columns(grp=Integer, deck_id=Uuid)
                .cte("summary_decks")
            )
            unique = (
                select(mapped.c.grp, DeckSense.sense_id)
                .join(DeckSense, DeckSense.deck_id == mapped.c.deck_id)
                .distinct()
                .cte("summary_senses")
            )
            query = (
                select(
                    unique.c.grp,
                    func.count().label("total"),
                    func.count(UserSense.sense_id).label("studied"),
                    func.count().filter(UserSense.due_at <= now).label("due"),
                    func.max(UserSense.last_exposure_at).label("last_studied_at"),
                )
                .outerjoin(
                    UserSense,
                    and_(UserSense.user_id == viewer_id, UserSense.sense_id == unique.c.sense_id),
                )
                .group_by(unique.c.grp)
            )
            aggregated = {int(r["grp"]): dict(r) for r in (await session.execute(query)).mappings()}
        result: list[dict[str, Any]] = []
        for scope in scopes.values():
            row = aggregated.get(
                group_ids[scope.root.id],
                {"total": 0, "studied": 0, "due": 0, "last_studied_at": None},
            )
            parent: UUID = (
                scope.root.reference_id
                if scope.root.type is NodeType.REFERENCE and scope.root.reference_id is not None
                else scope.root.id
            )
            children = [
                budget.metadata[i].type
                for i in budget.edges.get(parent, set())
                if i in scope.nodes and budget.metadata[i].parent_id == parent
            ]
            total: int = int(row["total"])
            studied: int = int(row["studied"])
            due: int = int(row["due"])
            result.append(
                {
                    "node_id": scope.root.id,
                    "as_of": now,
                    "total": total,
                    "new": total - studied if viewer_id else None,
                    "studied": studied if viewer_id else None,
                    "due": due if viewer_id else None,
                    "not_due": studied - due if viewer_id else None,
                    "last_studied_at": row["last_studied_at"] if viewer_id else None,
                    "coverage": studied / total if viewer_id and total else None,
                    "immediate_folders": children.count(NodeType.FOLDER),
                    "immediate_decks": children.count(NodeType.DECK),
                    "immediate_references": children.count(NodeType.REFERENCE),
                    "reachable_decks": len(scope.decks),
                }
            )
        by_id = {r["node_id"]: r for r in result}
        return result if node_ids == [None] else [by_id[i] for i in node_ids]


async def progress(
    session: AsyncSession,
    user: Actor,
    config: ProductConfig,
    node_id: UUID | None = None,
) -> dict[str, Any]:
    return (await summaries(session, user.id, config, [node_id]))[0]


def window(
    start: date | None,
    end: date | None,
    today: date,
    maximum: int,
    *,
    future: bool = False,
) -> tuple[date, date]:
    if (start is None) != (end is None):
        raise Problem(422, "invalid_date_window")
    if start is None:
        start, end = (
            (today, today + timedelta(days=maximum - 1))
            if future
            else (today - timedelta(days=maximum - 1), today)
        )
    assert start is not None and end is not None
    if end < start or (end - start).days >= maximum or (future and start < today):
        raise Problem(422, "invalid_date_window")
    return start, end


async def reporting(
    session: AsyncSession, user_id: UUID, config: ProductConfig
) -> tuple[str, datetime, date]:
    saved = await session.scalar(select(User.settings).where(User.id == user_id))
    if saved is None:
        raise Problem(404, "account_not_found")
    timezone = preferences(saved, config).timezone
    now = datetime.now(UTC)
    return timezone, now, now.astimezone(ZoneInfo(timezone)).date()


async def activity(
    session: AsyncSession,
    user_id: UUID,
    config: ProductConfig,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    timezone, now, today = await reporting(session, user_id, config)
    start, end = window(start_date, end_date, today, config.learning.limits.max_activity_days)
    rows = list(
        (
            await session.scalars(
                select(DailyActivity)
                .where(DailyActivity.user_id == user_id, DailyActivity.day.between(start, end))
                .order_by(DailyActivity.day)
            )
        ).all()
    )
    by_day = {r.day: r for r in rows}
    days: list[dict[str, Any]] = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        row = by_day.get(day)
        days.append(
            {
                "day": day,
                "applied_events": row.applied_events if row else 0,
                "practice_events": row.practice_events if row else 0,
            }
        )
    # Lifetime streaks stay in SQL; only the bounded date window reaches the application.
    active = (
        select(
            DailyActivity.day,
            (
                DailyActivity.day - func.row_number().over(order_by=DailyActivity.day).cast(Integer)
            ).label("island"),
        )
        .where(
            DailyActivity.user_id == user_id,
            DailyActivity.applied_events + DailyActivity.practice_events > 0,
        )
        .cte("active_days")
    )
    runs = (
        select(
            func.count().label("length"),
            func.count().filter(active.c.day <= today).label("current_length"),
            func.max(active.c.day).filter(active.c.day <= today).label("last_day"),
        )
        .group_by(active.c.island)
        .cte("activity_runs")
    )
    current_val, longest_val = (
        await session.execute(
            select(
                func.coalesce(
                    func.max(runs.c.current_length).filter(
                        runs.c.last_day >= today - timedelta(days=1)
                    ),
                    0,
                ),
                func.coalesce(func.max(runs.c.length), 0),
            )
        )
    ).one()
    return {
        "as_of": now,
        "timezone": timezone,
        "start_date": start,
        "end_date": end,
        "days": days,
        "applied_events": sum(d["applied_events"] for d in days),
        "practice_events": sum(d["practice_events"] for d in days),
        "current_streak": int(current_val),
        "longest_streak": int(longest_val),
    }


async def schedule(
    session: AsyncSession,
    user_id: UUID,
    config: ProductConfig,
    node_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    return (await schedules(session, user_id, config, [node_id], start_date, end_date))[0]


async def schedules(
    session: AsyncSession,
    user_id: UUID,
    config: ProductConfig,
    node_ids: Sequence[UUID | None],
    start_date: date | None = None,
    end_date: date | None = None,
    *,
    budget: ScopeBudget | None = None,
) -> list[dict[str, Any]]:
    if (
        not node_ids
        or len(node_ids) > config.learning.limits.max_summary_nodes
        or len(set(node_ids)) != len(node_ids)
    ):
        raise Problem(422, "invalid_summary_batch")
    timezone, now, today = await reporting(session, user_id, config)
    start, end = window(
        start_date, end_date, today, config.learning.limits.max_schedule_days, future=True
    )
    budget = budget or ScopeBudget(user_id)
    async with bounded(session, config, budget):
        resolved = await resolve_scopes(session, node_ids, user_id, config, budget=budget)
        scopes = (
            list(resolved.values())
            if None in node_ids
            else [resolved[i] for i in node_ids if i is not None]
        )
        group_ids, mapping = scope_mapping(scopes, budget, config)
        day = func.date(func.timezone(timezone, UserSense.due_at))
        mapped = (
            text(
                "SELECT unnest(CAST(:groups AS integer[])) AS grp, "
                "unnest(CAST(:decks AS uuid[])) AS deck_id"
            )
            .bindparams(groups=[g for g, _ in mapping], decks=[d for _, d in mapping])
            .columns(grp=Integer, deck_id=Uuid)
            .cte("schedule_decks")
        )
        unique = (
            select(mapped.c.grp, DeckSense.sense_id)
            .join(DeckSense, DeckSense.deck_id == mapped.c.deck_id)
            .distinct()
            .cte("schedule_senses")
        )
        rows = (
            await session.execute(
                select(unique.c.grp, day, func.count())
                .join(UserSense, UserSense.sense_id == unique.c.sense_id)
                .where(
                    UserSense.user_id == user_id,
                    UserSense.due_at > now,
                    day.between(start, end),
                )
                .group_by(unique.c.grp, day)
            )
        ).all()
        counts: dict[tuple[int, date], int] = {
            (int(r[0]), cast(date, r[1])): int(r[2]) for r in rows
        }
    return [
        {
            "node_id": scope.root.id,
            "as_of": now,
            "timezone": timezone,
            "start_date": start,
            "end_date": end,
            "days": [
                {
                    "day": start + timedelta(days=i),
                    "count": counts.get((group_ids[scope.root.id], start + timedelta(days=i)), 0),
                }
                for i in range((end - start).days + 1)
            ],
        }
        for scope in scopes
    ]
