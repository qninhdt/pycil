"""Worker config — reuses the API's Settings (same env vars: DB, redis, lexi)."""

from pycil.config import settings

__all__ = ["settings"]
