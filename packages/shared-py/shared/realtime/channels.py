"""Opaque async-resource channels shared by API and worker.

Authorization is enforced by the Centrifugo subscribe proxy against persisted
interests, not by channel names or user-limited channel suffixes.
"""

from uuid import UUID

_ASYNC_NS = "async"


def async_task(task_id: UUID | str) -> str:
    """Return the sole browser-visible channel form for a durable task."""
    return f"{_ASYNC_NS}:{task_id}"


def user_jobs(user_id: UUID | str, job_id: str) -> str:
    """Legacy channel retained until its producer migrates to durable tasks."""
    return f"users:{user_id}:jobs:{job_id}#{user_id}"


def user_grading(user_id: UUID | str, response_id: str) -> str:
    """Legacy channel retained until grading transitions use durable tasks."""
    return f"users:{user_id}:grading:{response_id}#{user_id}"
