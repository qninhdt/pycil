"""Admin moderation queue routes, gated by `AdminDep`.

`GET /admin-api/reports?status=pending` lists the queue.
`POST /admin-api/reports/{id}/resolve {action, note?}` resolves a report.

Resolution is single-transaction: content mutation + report-status update +
audit row commit together (red-team F7). All mounted under `/admin-api/reports`.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from pycil_core.api.deps import AdminDep, SessionDep
from pycil_core.middleware.rate_limit import enforce
from pycil_core.services import admin_audit_service, content_report_service

router = APIRouter(prefix="/admin-api/reports", tags=["admin-reports"])


class ResolveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(..., pattern="^(dismiss|delete_content)$")
    note: str | None = Field(default=None, max_length=500)


def _client_ip(request: Request) -> str | None:
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri
    return request.client.host if request.client else None


@router.get("")
async def list_reports(
    admin: AdminDep,
    session: SessionDep,
    status: str = "pending",
    limit: int = 100,
) -> dict:
    reports = await content_report_service.list_for_admin(
        session, status_filter=status, limit=limit
    )
    return {"reports": reports}


@router.post("/{report_id}/resolve")
async def resolve_report(
    report_id: int,
    body: ResolveBody,
    admin: AdminDep,
    session: SessionDep,
    request: Request,
) -> dict:
    await enforce(_client_ip(request) or "unknown", "admin_write")
    result = await content_report_service.resolve(
        session,
        report_id=report_id,
        admin_id=admin.id,
        action=body.action,
        note=body.note,
    )
    await admin_audit_service.record(
        session,
        actor_user_id=admin.id,
        action=f"resolve_report_{body.action}",
        metadata={"report_id": report_id, "note": body.note},
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return result
