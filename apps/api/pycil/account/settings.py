from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.models import User
from pycil.account.plans import Feature, Plan
from pycil.account.schemas import Preferences, PreferencesPatch
from pycil.app.config import AppConfig
from pycil.app.http import Problem
from pycil.study.config import LearningPreferences
from pycil.study.enums import ResponseFormat


def preferences(saved: dict[str, Any] | None, config: AppConfig) -> Preferences:
    raw = saved or {}
    defaults = config.product.account.preferences.defaults.model_dump()
    learning = config.product.study.defaults.model_dump() | raw.get("learning", {})
    assistant = defaults["assistant"] | raw.get("assistant", {})
    values = defaults | raw | {"learning": learning, "assistant": assistant}
    result = Preferences.model_validate(values)
    if result.locale not in config.product.account.preferences.locales:
        raise ValueError("unsupported locale")
    if result.translation_language not in config.product.account.preferences.translation_languages:
        raise ValueError("unsupported translation language")
    try:
        ZoneInfo(result.timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("invalid IANA timezone") from exc
    config.product.study.validate_limits(result.learning)
    return result


def effective_learning(saved: dict[str, Any], plan: Plan, config: AppConfig) -> LearningPreferences:
    selected = preferences(saved, config).learning
    formats = selected.formats
    if Feature.ADVANCED_GRADING not in config.product.account.plans[plan].features:
        formats = [ResponseFormat.SINGLE_CHOICE]
    try:
        effective = LearningPreferences.model_validate(selected.model_dump() | {"formats": formats})
        config.product.study.validate_preferences(effective)
    except ValueError as exc:
        raise Problem(422, "infeasible_learning_preferences") from exc
    return effective


def merge_preferences(
    saved: dict[str, Any], patch: PreferencesPatch, plan: Plan, config: AppConfig
) -> dict[str, Any]:
    changes = patch.model_dump(exclude_unset=True)
    nested = changes.pop("learning", None)
    assistant = changes.pop("assistant", None)
    merged = saved | changes
    if assistant is not None:
        merged["assistant"] = saved.get("assistant", {}) | assistant
    if nested is not None:
        if (
            "formats" in nested
            and Feature.ADVANCED_GRADING not in config.product.account.plans[plan].features
        ):
            if any(fmt != ResponseFormat.SINGLE_CHOICE for fmt in nested["formats"]):
                raise Problem(403, "advanced_grading_not_available")
        merged["learning"] = saved.get("learning", {}) | nested
    try:
        effective_learning(merged, plan, config)
    except (ValueError, Problem) as exc:
        raise Problem(422, "invalid_preferences") from exc
    return merged


async def update_preferences(
    session: AsyncSession,
    user_id: UUID,
    patch: PreferencesPatch,
    config: AppConfig,
) -> User:
    async with session.begin():
        user = await session.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        if user is None:
            raise Problem(404, "account_not_found")
        user.settings = merge_preferences(user.settings, patch, user.plan, config)
        await session.flush()
    return user
