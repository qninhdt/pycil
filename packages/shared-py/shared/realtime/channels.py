"""Owner-scoped Centrifugo channel names — shared by API and worker.

Every channel retains the readable ``users:{uid}:...`` prefix and terminates
with Centrifugo's native user-limited ``#{uid}`` boundary. Centrifugo v5
enforces that boundary against the authenticated connection subject.
"""

from uuid import UUID

_USER_NS = "users"


def user_notifications(user_id: UUID | str) -> str:
    return f"{_USER_NS}:{user_id}#{user_id}"


def user_jobs(user_id: UUID | str, job_id: str) -> str:
    return f"{_USER_NS}:{user_id}:jobs:{job_id}#{user_id}"


def user_grading(user_id: UUID | str, response_id: str) -> str:
    return f"{_USER_NS}:{user_id}:grading:{response_id}#{user_id}"


def user_channel_pattern(user_id: UUID | str) -> str:
    """Readable prefix shared by all of a user's channels."""
    return f"{_USER_NS}:{user_id}:"
