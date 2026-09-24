"""Authenticated account credit, export and deletion routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account import credit, service
from pycil.account.schemas import AccountCredit, AccountDeleteRequest, AccountExport
from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import UnauthorizedError
from pycil.db.session import get_session

router = APIRouter(tags=["account"])


@router.get("/me/credit", response_model=AccountCredit)
async def read_credit(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> AccountCredit:
    """The caller's monthly allowance, in Credits rather than currency.

    Read-only: the snapshot reflects an elapsed period roll without persisting it,
    because a learner opening the app should not be the event that renews their
    month. The debit path owns that write.
    """
    current = await credit.snapshot(session, user.id)
    return AccountCredit(
        plan=current.plan,
        balance=current.balance,
        available=max(0, current.balance),
        period_start=current.period_start,
        period_end=current.period_end,
        period_used=current.period_used,
        period_grant=current.grant,
        topup_balance=current.topup_balance,
    )


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
    await service.delete_account(session, user.id)
    return Response(status_code=204)
