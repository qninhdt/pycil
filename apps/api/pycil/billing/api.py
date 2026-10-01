"""Authenticated allowance and legacy credit endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.auth import current_user
from pycil.account.schemas import CurrentUser
from pycil.billing.ledger import get_usage_allowance
from pycil.billing.schemas import CreditBalanceResponse, UsageAllowanceResponse
from pycil.platform.database import get_session

router = APIRouter(tags=["billing"])


@router.get("/me/usage", response_model=UsageAllowanceResponse)
async def read_usage(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> UsageAllowanceResponse:
    allowance = await get_usage_allowance(session, user.id)
    return UsageAllowanceResponse(
        plan=allowance.plan,
        period_start=allowance.period_start,
        period_end=allowance.period_end,
        allowance_units=allowance.allowance_units,
        used_units=allowance.used_units,
        remaining_units=allowance.remaining_units,
    )


@router.get("/me/credits", response_model=CreditBalanceResponse)
async def read_credits(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> CreditBalanceResponse:
    allowance = await get_usage_allowance(session, user.id)
    return CreditBalanceResponse(
        plan=allowance.plan,
        period_start=allowance.period_start,
        period_end=allowance.period_end,
        allowance_units=allowance.allowance_units,
        consumed_units=allowance.used_units,
        available_units=allowance.remaining_units,
    )
