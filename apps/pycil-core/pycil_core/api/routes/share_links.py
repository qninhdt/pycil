"""Share link HTTP API: create + revoke + list per node."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.services import share_link_service


router = APIRouter(prefix="/nodes", tags=["share-links"])


class ShareLinkOut(BaseModel):
    id: str
    token: str
    created_at: str
    revoked_at: str | None = None


async def _assert_owner(session, *, node_id: UUID, user_id: UUID) -> None:
    row = (
        await session.execute(
            text("SELECT author_id FROM nodes WHERE id = :nid"),
            {"nid": node_id},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "node_not_found")
    if row.author_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_owner")


@router.post("/{node_id}/share-links", response_model=ShareLinkOut)
async def create_share_link(
    node_id: UUID, user: UserDep, session: SessionDep
) -> ShareLinkOut:
    await _assert_owner(session, node_id=node_id, user_id=user.id)
    row = await share_link_service.create_link(
        session, node_id=node_id, created_by=user.id
    )
    return ShareLinkOut(**row)


@router.get("/{node_id}/share-links", response_model=list[ShareLinkOut])
async def list_share_links(
    node_id: UUID, user: UserDep, session: SessionDep
) -> list[ShareLinkOut]:
    await _assert_owner(session, node_id=node_id, user_id=user.id)
    rows = await share_link_service.list_for_node(
        session, node_id=node_id, user_id=user.id
    )
    return [ShareLinkOut(**r) for r in rows]


@router.delete("/share-links/{link_id}")
async def revoke_share_link(
    link_id: UUID, user: UserDep, session: SessionDep
) -> dict:
    ok = await share_link_service.revoke_link(
        session, link_id=link_id, user_id=user.id
    )
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "link_not_found")
    return {"revoked": True}
