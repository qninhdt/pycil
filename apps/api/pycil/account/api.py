"""Authenticated profile, export, and deletion routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.auth import current_user
from pycil.account.deletion import delete_account
from pycil.account.export import export_account
from pycil.account.schemas import (
    AccountDeleteRequest,
    AccountExport,
    CapabilitiesRead,
    CurrentUser,
    ViewerRead,
)
from pycil.platform.database import get_session
from pycil.platform.errors import UnauthorizedError
from pycil.platform.settings import settings

router = APIRouter(tags=["account"])


@router.get("/me", response_model=ViewerRead)
async def me(user: Annotated[CurrentUser, Depends(current_user)]) -> ViewerRead:
    """The caller's authenticated user profile projection."""
    return ViewerRead(id=user.id, email=user.email, name=user.name, image=user.image)


@router.get("/capabilities", response_model=CapabilitiesRead)
async def capabilities() -> CapabilitiesRead:
    """System capabilities available in the current environment."""
    return CapabilitiesRead(
        assistant=bool(settings.assistant_api_key and settings.assistant_base_url)
    )


@router.get("/me/export", response_model=AccountExport)
async def export_me(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> AccountExport:
    return AccountExport.model_validate(await export_account(session, user.id))


@router.delete("/me", status_code=204)
async def delete_me(
    body: AccountDeleteRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> Response:
    if body.confirmation != "DELETE":
        raise UnauthorizedError("account_delete_confirmation_required")
    await delete_account(session, user.id)
    return Response(status_code=204)
