"""Owner-scoped Centrifugo channel names — shared by api + worker.

EVERY private channel is prefixed ``users:{uid}:...`` so Centrifugo's per-user
namespace permission authorizes a token to subscribe ONLY to its own channels.
``jobs``/``grading`` ids are enumerable bigints, so unprefixed channels would
leak another user's stream — the uid prefix is the security boundary.
"""

from uuid import UUID

# Centrifugo namespace: config grants subscribe only to `users:{sub}:*` for the
# token's subject, so the uid prefix is enforced server-side, not just by name.
_USER_NS = "users"


def user_notifications(user_id: UUID | str) -> str:
    return f"{_USER_NS}:{user_id}"


def user_jobs(user_id: UUID | str, job_id: str) -> str:
    return f"{_USER_NS}:{user_id}:jobs:{job_id}"


def user_grading(user_id: UUID | str, response_id: str) -> str:
    return f"{_USER_NS}:{user_id}:grading:{response_id}"


def user_channel_pattern(user_id: UUID | str) -> str:
    """The channel prefix a user's subscription token is scoped to."""
    return f"{_USER_NS}:{user_id}"
