"""Share link HTTP API: create + revoke + list per node."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.services import share_link_service
from pycil_core.services._node_access import assert_node_owner


router = APIRouter(prefix="/nodes", tags=["share-links"])


class ShareLinkOut(BaseModel):
    id: str
    token: str
    created_at: str
    revoked_at: str | None = None


@router.post("/{node_id}/share-links", response_model=ShareLinkOut)
async def create_share_link(
    node_id: UUID, user: UserDep, session: SessionDep
) -> ShareLinkOut:
    await assert_node_owner(session, node_id=node_id, user_id=user.id)
    row = await share_link_service.create_link(
        session, node_id=node_id, created_by=user.id
    )
    return ShareLinkOut(**row)


@router.get("/{node_id}/share-links", response_model=list[ShareLinkOut])
async def list_share_links(
    node_id: UUID, user: UserDep, session: SessionDep
) -> list[ShareLinkOut]:
    await assert_node_owner(session, node_id=node_id, user_id=user.id)
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
