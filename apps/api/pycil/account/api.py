from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from pycil.account.auth import UserId, Viewer
from pycil.account.models import User
from pycil.account.profiles import profile, public_projection, update_profile
from pycil.account.schemas import Allowance, PreferencesPatch, Profile, ProfilePatch, PublicProfile
from pycil.account.settings import update_preferences
from pycil.account.usage import allowance
from pycil.app.dependencies import Config, Session
from pycil.app.http import Problem
from pycil.infrastructure.observability import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/me", tags=["account"])
public_router = APIRouter(prefix="/v1/users", tags=["profiles"])


@router.get("", response_model=Profile)
async def me(user: UserId, config: Config, session: Session):
    return await profile(user, config, session)


@router.patch("/settings", response_model=Profile)
async def patch_settings(
    patch: PreferencesPatch, user_id: UserId, config: Config, session: Session
):
    user = await update_preferences(session, user_id, patch, config)
    return await profile(user.id, config, session)


@router.patch("/profile", response_model=Profile)
async def edit_profile(data: ProfilePatch, user_id: UserId, config: Config, session: Session):
    user = await update_profile(session, user_id, data)
    return await profile(user.id, config, session)


@public_router.get(":lookup", response_model=PublicProfile, openapi_extra={"security": [{}]})
async def by_handle(handle: str, session: Session, viewer: Viewer):
    return await public_projection(
        await session.scalar(select(User).where(User.handle == handle.strip().lower())), session
    )


@public_router.get("/{user_id}", response_model=PublicProfile, openapi_extra={"security": [{}]})
async def public_profile(user_id: UUID, session: Session, viewer: Viewer):
    return await public_projection(await session.get(User, user_id), session)


@router.get("/usage", response_model=Allowance)
async def usage(user_id: UserId, config: Config, session: Session):
    async with session.begin():
        user = await session.scalar(
            select(User).where(User.id == user_id).execution_options(populate_existing=True)
        )
        if user is None:
            raise Problem(404, "account_not_found")
        return await allowance(session, user, config, datetime.now(UTC))
