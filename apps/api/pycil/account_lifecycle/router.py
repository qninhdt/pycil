"""Authenticated account export and deletion routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account_lifecycle import service
from pycil.account_lifecycle.schemas import AccountDeleteRequest, AccountExport
from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import UnauthorizedError
from pycil.db.session import get_session
from pycil.ports.centrifugo import disconnect_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["account"])


@router.get("/me/export", response_model=AccountExport)
async def export_me(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> AccountExport:
    return AccountExport.model_validate(await service.export_account(session, user.id))


@router.delete("/me", status_code=204)
async def delete_me(
    body: AccountDeleteRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> Response:
    if body.confirmation != "DELETE":
        raise UnauthorizedError("account_delete_confirmation_required")
    if not await service.owns_active_refresh_token(session, user.id, body.refresh_token):
        raise UnauthorizedError("invalid_refresh_token")
    await service.delete_account(session, user.id)
    # The account rows are gone either way; a socket that outlives them can only
    # observe channels whose interests were deleted with it. Logged rather than
    # discarded so an operator can see when that cleanup did not land.
    if not await disconnect_user(user.id):
        logger.warning(
            "realtime disconnect failed after account deletion",
            extra={"user_id": str(user.id)},
        )
    return Response(status_code=204)
