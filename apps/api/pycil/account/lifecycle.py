"""Identity verification and short-lived account existence checks."""

from urllib.parse import quote

import httpx
from sqlalchemy import select

from pycil.account.models import User
from pycil.http import Problem
from pycil.logging import get_logger

logger = get_logger(__name__)


async def clerk_user(http, deployment, subject):
    try:
        response = await http.request(
            "GET",
            "https://api.clerk.com/v1/users/" + quote(subject, safe=""),
            headers={"Authorization": "Bearer " + deployment.clerk_secret_key.get_secret_value()},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        logger.error("clerk_api_request_failed", error_type=type(exc).__name__, subject=subject)
        raise Problem(503, "identity_service_unavailable") from None
    if response.status_code == 404:
        logger.warning("clerk_user_not_found", subject=subject)
        raise Problem(401, "invalid_credentials")
    if not response.is_success:
        logger.error("clerk_api_request_failed", status_code=response.status_code, subject=subject)
        raise Problem(503, "identity_service_unavailable")
    try:
        data = response.json()
        if not isinstance(data, dict) or any(
            data.get(key) is not None and not isinstance(data[key], str)
            for key in ("first_name", "last_name")
        ):
            raise ValueError("invalid identity profile")
    except ValueError as exc:
        logger.error("clerk_api_request_failed", error_type=type(exc).__name__, subject=subject)
        raise Problem(503, "identity_service_unavailable") from None
    return data


def row_data(row):
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.computed is None
    }


async def require_user(session, user_id):
    """Check the account without serializing unrelated user writes."""
    user = await session.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update(read=True, key_share=True)
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise Problem(404, "account_not_found")
    return user


async def invalidate_actor(session, user):
    if cache := session.info.get("cache"):
        await cache.discard(f"actor:v3:{user.clerk_subject}")
