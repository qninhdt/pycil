from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select

from pycil.account.auth import Actor
from pycil.account.lifecycle import invalidate_actor
from pycil.account.models import User
from pycil.account.schemas import (
    PreferencesPatch,
    effective_learning,
    merge_preferences,
    preferences,
)
from pycil.account.usage import allowance
from pycil.dependencies import Product, Session
from pycil.http import Problem

router = APIRouter(prefix="/v1/me", tags=["account"])


def profile(user, config):
    resolved = preferences(user.settings, config)
    try:
        effective = effective_learning(user.settings, user.plan, config)
        learning = effective.model_dump(mode="json")
        restriction = None
    except Problem as exc:
        learning, restriction = None, exc.code
    return {
        "id": user.id,
        "display_name": user.display_name,
        "plan": user.plan,
        "settings": resolved.model_dump(mode="json"),
        "effective_learning": learning,
        "learning_restriction": restriction,
    }


@router.get("")
async def me(user: Actor, config: Product):
    return profile(user, config)


@router.patch("/settings")
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
        result = profile(user, config)
    await invalidate_actor(session, user)
    return result


@router.get("/usage")
async def usage(actor: Actor, config: Product, session: Session):
    async with session.begin():
        user = await session.scalar(
            select(User).where(User.id == actor.id).execution_options(populate_existing=True)
        )
        if user is None:
            raise Problem(404, "account_not_found")
        return await allowance(session, user, config, datetime.now(UTC))
