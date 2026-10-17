from typing import cast
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.config import AccountConfig
from pycil.account.models import User
from pycil.account.plans import Feature, Plan
from pycil.account.schemas import Preferences, PreferencesPatch
from pycil.study.config import LearningPreferences, StudyConfig
from pycil.study.enums import ResponseFormat
from pycil.utils.errors import Forbidden, InvalidInput, NotFound, OperationError


def preferences(
    saved: dict[str, object] | None,
    account_config: AccountConfig,
    study_config: StudyConfig,
) -> Preferences:
    raw = saved or {}
    default_assistant: dict[str, object] = {"auto_approve": account_config.auto_approve_assistant}
    defaults: dict[str, object] = {
        "locale": account_config.default_locale,
        "timezone": account_config.default_timezone,
        "translation_language": account_config.default_translation_language,
        "assistant": default_assistant,
    }
    raw_learning = raw.get("learning")
    learning = study_config.defaults.model_dump() | (
        cast(dict[str, object], raw_learning) if isinstance(raw_learning, dict) else {}
    )
    raw_assistant = raw.get("assistant")
    assistant: dict[str, object] = default_assistant | (
        cast(dict[str, object], raw_assistant) if isinstance(raw_assistant, dict) else {}
    )
    values: dict[str, object] = defaults | raw | {"learning": learning, "assistant": assistant}
    result = Preferences.model_validate(values)
    if result.locale not in account_config.locales:
        raise ValueError("unsupported locale")
    if result.translation_language not in account_config.translation_languages:
        raise ValueError("unsupported translation language")
    try:
        ZoneInfo(result.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("invalid IANA timezone") from exc
    study_config.validate_limits(result.learning)
    return result


def effective_learning(
    saved: dict[str, object],
    plan: Plan,
    account_config: AccountConfig,
    study_config: StudyConfig,
) -> LearningPreferences:
    selected = preferences(saved, account_config, study_config).learning
    formats = selected.formats
    if Feature.ADVANCED_GRADING not in account_config.plans[plan].features:
        formats = [ResponseFormat.SINGLE_CHOICE]
    try:
        effective = LearningPreferences.model_validate(selected.model_dump() | {"formats": formats})
        study_config.validate_preferences(effective)
    except ValueError as exc:
        raise InvalidInput("infeasible_learning_preferences") from exc
    return effective


def merge_preferences(
    saved: dict[str, object],
    patch: PreferencesPatch,
    plan: Plan,
    account_config: AccountConfig,
    study_config: StudyConfig,
) -> dict[str, object]:
    changes = patch.model_dump(exclude_unset=True)
    nested = changes.pop("learning", None)
    assistant = changes.pop("assistant", None)
    merged = saved | changes
    if assistant is not None:
        merged["assistant"] = saved.get("assistant", {}) | assistant
    if nested is not None:
        if (
            "formats" in nested
            and Feature.ADVANCED_GRADING not in account_config.plans[plan].features
        ):
            if any(fmt != ResponseFormat.SINGLE_CHOICE for fmt in nested["formats"]):
                raise Forbidden("advanced_grading_not_available")
        merged["learning"] = saved.get("learning", {}) | nested
    try:
        effective_learning(merged, plan, account_config, study_config)
    except (ValueError, OperationError) as exc:
        raise InvalidInput("invalid_preferences") from exc
    return merged


async def update_preferences(
    session: AsyncSession,
    user_id: UUID,
    patch: PreferencesPatch,
    account_config: AccountConfig,
    study_config: StudyConfig,
) -> User:
    async with session.begin():
        user = await session.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        if user is None:
            raise NotFound("account_not_found")
        user.settings = merge_preferences(
            user.settings, patch, user.plan, account_config, study_config
        )
        await session.flush()
    return user
