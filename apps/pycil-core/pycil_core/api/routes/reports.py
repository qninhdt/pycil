"""User-facing content report endpoint.

`POST /reports` lets an authenticated user report a public deck or a definition
comment. Rate-limited; the service validates the target and forbids self-report
+ duplicate pending reports. Stays under `/reports` (NOT `/admin-api`).
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.middleware.rate_limit import client_ip, enforce
from pycil_core.services import content_report_service

router = APIRouter(prefix="/reports", tags=["reports"])


class CreateReportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content_type: str = Field(..., pattern="^(deck|comment)$")
    content_id: str = Field(..., min_length=1, max_length=64)
    reason: str = Field(..., min_length=1, max_length=200)
    details: str | None = Field(default=None, max_length=2000)


@router.post("")
async def create_report(
    body: CreateReportBody,
    user: UserDep,
    session: SessionDep,
    request: Request,
) -> dict:
    await enforce(client_ip(request), "create_report")
    report_id = await content_report_service.create(
        session,
        reporter_user_id=user.id,
        content_type=body.content_type,
        content_id=body.content_id,
        reason=body.reason,
        details=body.details,
    )
    await session.commit()
    return {"report_id": report_id, "status": "pending"}
