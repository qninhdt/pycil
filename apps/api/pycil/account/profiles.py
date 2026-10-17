from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.config import AccountConfig
from pycil.account.models import User
from pycil.account.plans import Feature
from pycil.account.schemas import ProfilePatch
from pycil.account.settings import effective_learning, preferences
from pycil.account.types import ProfileData, PublicProfileData
from pycil.library.models import NodeRole
from pycil.library.tree import roots
from pycil.observability import get_logger
from pycil.study.config import StudyConfig
from pycil.utils.errors import Conflict, NotFound, OperationError

logger = get_logger(__name__)


async def profile(
    user_id: UUID,
    account_config: AccountConfig,
    study_config: StudyConfig,
    session: AsyncSession,
) -> ProfileData:
    selected = await session.scalar(
        select(User).where(User.id == user_id).execution_options(populate_existing=True)
    )
    if selected is None:
        raise NotFound("account_not_found")
    current_user: User = selected
    resolved = preferences(current_user.settings, account_config, study_config)
    try:
        effective = effective_learning(
            current_user.settings, current_user.plan, account_config, study_config
        )
        learning: dict[str, object] | None = effective.model_dump(mode="json")
        restriction: str | None = None
    except OperationError as exc:
        learning, restriction = None, exc.code
    system = await roots(session, current_user.id)
    return {
        "id": current_user.id,
        "display_name": current_user.display_name,
        "handle": current_user.handle,
        "bio": current_user.bio,
        "joined_at": current_user.created_at,
        "learning_options": {
            "pairs": [
                {"question_type": kind, "format": fmt, "level": level}
                for kind, formats in study_config.pair_levels.items()
                for fmt, level in formats.items()
            ],
            "limits": study_config.limits.model_dump(),
            "advanced_grading": Feature.ADVANCED_GRADING
            in account_config.plans[current_user.plan].features,
        },
        "plan": current_user.plan,
        "settings": resolved.model_dump(mode="json"),
        "effective_learning": learning,
        "learning_restriction": restriction,
        "library_node_id": system[NodeRole.LIBRARY_ROOT].id,
        "personal_node_id": system[NodeRole.PERSONAL_ROOT].id,
        "published_node_id": system[NodeRole.PUBLISHED_ROOT].id,
    }


async def public_projection(user: User | None, session: AsyncSession) -> PublicProfileData:
    if user is None:
        raise NotFound("account_not_found")
    system = await roots(session, user.id)
    return {
        "id": user.id,
        "display_name": user.display_name,
        "handle": user.handle,
        "bio": user.bio,
        "joined_at": user.created_at,
        "published_node_id": system[NodeRole.PUBLISHED_ROOT].id,
    }


async def update_profile(session: AsyncSession, user_id: UUID, data: ProfilePatch) -> User:
    try:
        async with session.begin():
            user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                raise NotFound("account_not_found")
            for key, value in data.model_dump(exclude_unset=True).items():
                setattr(user, key, value)
            await session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23505":
            logger.warning("account_handle_conflict", handle=data.handle)
            raise Conflict("handle_unavailable") from None
        raise
    return user

