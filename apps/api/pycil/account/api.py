from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pycil.account.auth import Actor, Viewer
from pycil.account.lifecycle import invalidate_actor
from pycil.account.models import User
from pycil.account.plans import Feature
from pycil.account.schemas import (
    Allowance,
    PreferencesPatch,
    Profile,
    ProfilePatch,
    PublicProfile,
    effective_learning,
    merge_preferences,
    preferences,
)
from pycil.account.usage import allowance
from pycil.dependencies import Product, Session
from pycil.http import Problem
from pycil.library.models import NodeRole
from pycil.library.tree import roots
from pycil.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/me", tags=["account"])
public_router = APIRouter(prefix="/v1/users", tags=["profiles"])


async def profile(user, config, session):
    user = await session.scalar(
        select(User).where(User.id == user.id).execution_options(populate_existing=True)
    )
    if user is None:
        raise Problem(404, "account_not_found")
    resolved = preferences(user.settings, config)
    try:
        effective = effective_learning(user.settings, user.plan, config)
        learning = effective.model_dump(mode="json")
        restriction = None
    except Problem as exc:
        learning, restriction = None, exc.code
    system = await roots(session, user.id)
    return {
        "id": user.id,
        "display_name": user.display_name,
        "handle": user.handle,
        "bio": user.bio,
        "joined_at": user.created_at,
        "learning_options": {
            "pairs": [
                {"question_type": kind, "format": fmt, "level": level}
                for kind, formats in config.learning.pair_levels.items()
                for fmt, level in formats.items()
            ],
            "limits": config.learning.limits.model_dump(),
            "advanced_grading": Feature.ADVANCED_GRADING in config.plans[user.plan].features,
        },
        "plan": user.plan,
        "settings": resolved.model_dump(mode="json"),
        "effective_learning": learning,
        "learning_restriction": restriction,
        "library_node_id": system[NodeRole.LIBRARY_ROOT].id,
        "personal_node_id": system[NodeRole.PERSONAL_ROOT].id,
        "published_node_id": system[NodeRole.PUBLISHED_ROOT].id,
    }


@router.get("", response_model=Profile)
async def me(user: Actor, config: Product, session: Session):
    return await profile(user, config, session)


@router.patch("/settings", response_model=Profile)
async def patch_settings(patch: PreferencesPatch, actor: Actor, config: Product, session: Session):
    async with session.begin():
        user = await session.scalar(
            select(User)
            .where(User.id == actor.id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        if user is None:
            raise Problem(404, "account_not_found")
        user.settings = merge_preferences(user.settings, patch, user.plan, config)
        await session.flush()
        result = await profile(user, config, session)
    await invalidate_actor(session, user)
    return result


async def public_projection(user, session):
    if user is None:
        raise Problem(404, "account_not_found")
    system = await roots(session, user.id)
    return {
        "id": user.id,
        "display_name": user.display_name,
        "handle": user.handle,
        "bio": user.bio,
        "joined_at": user.created_at,
        "published_node_id": system[NodeRole.PUBLISHED_ROOT].id,
    }


@router.patch("/profile", response_model=Profile)
async def edit_profile(data: ProfilePatch, actor: Actor, config: Product, session: Session):
    try:
        async with session.begin():
            user = await session.scalar(select(User).where(User.id == actor.id).with_for_update())
            if user is None:
                raise Problem(404, "account_not_found")
            for key, value in data.model_dump(exclude_unset=True).items():
                setattr(user, key, value)
            await session.flush()
            result = await profile(user, config, session)
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23505":
            logger.warning("account_handle_conflict", handle=data.handle)
            raise Problem(409, "handle_unavailable") from None
        raise
    await invalidate_actor(session, user)
    return result


@public_router.get(":lookup", response_model=PublicProfile, openapi_extra={"security": [{}]})
async def by_handle(handle: str, session: Session, viewer: Viewer):
    return await public_projection(
        await session.scalar(select(User).where(User.handle == handle.strip().lower())), session
    )


@public_router.get("/{user_id}", response_model=PublicProfile, openapi_extra={"security": [{}]})
async def public_profile(user_id: UUID, session: Session, viewer: Viewer):
    return await public_projection(await session.get(User, user_id), session)


@router.get("/usage", response_model=Allowance)
async def usage(actor: Actor, config: Product, session: Session):
    async with session.begin():
        user = await session.scalar(
            select(User).where(User.id == actor.id).execution_options(populate_existing=True)
        )
        if user is None:
            raise Problem(404, "account_not_found")
        return await allowance(session, user, config, datetime.now(UTC))
