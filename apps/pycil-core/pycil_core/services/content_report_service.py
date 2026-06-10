"""Content-report moderation pipeline.

Users report public decks / definition comments; admins triage and resolve.

Security (red-team F9/F3): never trust the reporter-supplied target. At
`create` the wire `content_id` is validated against the type's key space
(UUID for deck, BIGINT for comment) and written to the typed `node_id` /
`comment_id` column; the target's owner + a title snapshot are recorded. At
`resolve` the target is re-fetched by its typed FK and matched against the
snapshot before any soft-delete. All queries parameterized.

Transactions (F7): mutators do NOT commit — the route owns the unit of work so
the content mutation + report-status update + audit row commit together.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from shared.db import ContentReport, DefinitionComment, Node
from sqlalchemy import func, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from pycil_core.services import definition_comments_service, node_service

VALID_CONTENT_TYPES = {"deck", "comment"}


async def _resolve_deck_target(session: AsyncSession, content_id: str) -> tuple[UUID, dict]:
    """Validate a deck content_id (UUID) and snapshot owner + name."""
    try:
        node_uuid = UUID(content_id)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_content_id") from exc
    row = (
        await session.exec(
            select(Node.author_id, Node.name).where(Node.id == node_uuid)
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "content_not_found")
    return node_uuid, {"owner_id": str(row.author_id), "name": row.name}


async def _resolve_comment_target(session: AsyncSession, content_id: str) -> tuple[int, dict]:
    """Validate a comment content_id (BIGINT) and snapshot owner + body excerpt."""
    try:
        comment_id = int(content_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_content_id") from exc
    row = (
        await session.exec(
            select(
                DefinitionComment.author_id, DefinitionComment.body
            ).where(
                DefinitionComment.id == comment_id,
                DefinitionComment.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "content_not_found")
    return comment_id, {"owner_id": str(row.author_id), "excerpt": (row.body or "")[:80]}


async def create(
    session: AsyncSession,
    *,
    reporter_user_id: UUID,
    content_type: str,
    content_id: str,
    reason: str,
    details: str | None,
) -> int:
    """Create a pending report. Caller commits. Raises on guard violations."""
    if content_type not in VALID_CONTENT_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_content_type")

    node_id: UUID | None = None
    comment_id: int | None = None
    if content_type == "deck":
        node_id, snapshot = await _resolve_deck_target(session, content_id)
    else:
        comment_id, snapshot = await _resolve_comment_target(session, content_id)

    owner_id = UUID(snapshot["owner_id"]) if snapshot.get("owner_id") else None
    if owner_id == reporter_user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot_report_own_content")

    report = ContentReport(
        reporter_user_id=reporter_user_id,
        content_type=content_type,
        node_id=node_id,
        comment_id=comment_id,
        reason=reason,
        details=details,
        status="pending",
        target_owner_id=owner_id,
        target_snapshot=snapshot,
    )
    session.add(report)
    try:
        await session.flush()
    except Exception as exc:  # noqa: BLE001
        # Partial-unique pending index → duplicate pending report.
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "duplicate_pending_report"
        ) from exc
    return int(report.id or 0)


async def list_for_admin(
    session: AsyncSession, *, status_filter: str = "pending", limit: int = 100
) -> list[dict]:
    rows = (
        await session.exec(
            select(
                ContentReport.id,
                ContentReport.reporter_user_id,
                ContentReport.content_type,
                ContentReport.node_id,
                ContentReport.comment_id,
                ContentReport.reason,
                ContentReport.details,
                ContentReport.status,
                ContentReport.target_owner_id,
                ContentReport.target_snapshot,
                ContentReport.created_at,
            )
            .where(ContentReport.status == status_filter)
            .order_by(ContentReport.created_at.desc())
            .limit(min(max(limit, 1), 500))
        )
    ).all()
    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "id": int(r.id),
                "reporter_user_id": str(r.reporter_user_id),
                "content_type": r.content_type,
                "node_id": str(r.node_id) if r.node_id else None,
                "comment_id": int(r.comment_id) if r.comment_id is not None else None,
                "reason": r.reason,
                "details": r.details,
                "status": r.status,
                "target_owner_id": str(r.target_owner_id) if r.target_owner_id else None,
                "target_snapshot": r.target_snapshot,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return out


async def _get_report(session: AsyncSession, report_id: int) -> ContentReport | None:
    # session.get returns the mapped instance by PK (sqlalchemy `select(Model)`
    # + sqlmodel exec would yield a Row, not the model).
    return await session.get(ContentReport, report_id)


async def resolve(
    session: AsyncSession,
    *,
    report_id: int,
    admin_id: UUID,
    action: str,
    note: str | None = None,
) -> dict:
    """Resolve a pending report. Caller owns the transaction (single commit).

    action ∈ {dismiss, delete_content}. For delete_content the target is
    re-fetched by its typed FK and matched against the recorded snapshot before
    soft-deletion (F9).
    """
    if action not in {"dismiss", "delete_content"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_action")

    report = await _get_report(session, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "report_not_found")
    if report.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "report_already_resolved")

    resolution = "dismissed"
    if action == "delete_content":
        # 2-arm dispatch on content_type (no abstraction — red-team F7).
        if report.content_type == "deck":
            await _verify_and_delete_deck(session, report)
        elif report.content_type == "comment":
            await _verify_and_delete_comment(session, report, admin_id)
        else:  # pragma: no cover - create() rejects other types
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_content_type")
        resolution = "actioned"

    await session.exec(
        update(ContentReport)
        .where(ContentReport.id == report_id)
        .values(
            status="dismissed" if action == "dismiss" else "actioned",
            resolved_by=admin_id,
            resolved_at=func.now(),
            resolution=note or resolution,
        )
    )
    return {
        "report_id": report_id,
        "status": "dismissed" if action == "dismiss" else "actioned",
    }


async def _verify_and_delete_deck(session: AsyncSession, report: ContentReport) -> None:
    if report.node_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "report_target_missing")
    row = (
        await session.exec(
            select(Node.author_id).where(Node.id == report.node_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "target_gone")
    snap = report.target_snapshot or {}
    if snap.get("owner_id") and str(row.author_id) != snap["owner_id"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "target_changed")
    await node_service.admin_soft_delete_node(session, report.node_id)


async def _verify_and_delete_comment(
    session: AsyncSession, report: ContentReport, admin_id: UUID
) -> None:
    if report.comment_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "report_target_missing")
    row = (
        await session.exec(
            select(DefinitionComment.author_id).where(
                DefinitionComment.id == report.comment_id
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "target_gone")
    snap = report.target_snapshot or {}
    if snap.get("owner_id") and str(row.author_id) != snap["owner_id"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "target_changed")
    await definition_comments_service.soft_delete(
        session, report.comment_id, actor_id=admin_id, is_admin=True
    )


async def count_reports_against(session: AsyncSession, *, owner_id: UUID) -> int:
    """Count reports where this user is the target owner."""
    row = (
        await session.exec(
            select(func.count())
            .select_from(ContentReport)
            .where(ContentReport.target_owner_id == owner_id)
        )
    ).one()
    # sqlalchemy `select` via sqlmodel `.exec()` yields a Row → index the scalar.
    return int(row[0])
