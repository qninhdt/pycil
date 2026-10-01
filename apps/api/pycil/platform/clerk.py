"""Clerk SDK platform client and connection pool lifecycle."""

from clerk_backend_api import Clerk

from pycil.platform.errors import ServiceUnavailableError
from pycil.platform.settings import settings

_clerk_client: Clerk | None = None


def get_clerk_client() -> Clerk:
    """Return the shared Clerk SDK client instance.

    Uses a callable for ``bearer_auth`` so dynamic secret key changes or test
    monkeypatches take effect without tearing down the underlying HTTP connection pool.
    """
    global _clerk_client
    if not settings.clerk_secret_key:
        raise ServiceUnavailableError("clerk_not_configured")
    if _clerk_client is None:
        _clerk_client = Clerk(bearer_auth=lambda: settings.clerk_secret_key)
    return _clerk_client


def reset_clerk_client() -> None:
    """Reset the singleton instance (primarily for testing)."""
    global _clerk_client
    _clerk_client = None
