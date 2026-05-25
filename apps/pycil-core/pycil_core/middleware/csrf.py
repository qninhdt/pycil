"""Origin-allowlist CSRF middleware.

Auth.js cookies are SameSite=Strict but we add an Origin allowlist as a second
layer. Mutating methods (POST/PATCH/PUT/DELETE) are rejected if Origin is
missing/disallowed AND Referer is missing/disallowed.

Internal callers (Auth.js callback) hit `/auth/*` with X-Internal-Secret and
no browser Origin. Bypass is scoped to `/auth/*` to keep the surface tiny.
"""
from __future__ import annotations

import hmac
import logging
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from pycil_core.config import get_settings

_MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}
_INTERNAL_BYPASS_PREFIX = "/auth/"
_log = logging.getLogger(__name__)


def _normalize_origin(value: str) -> str:
    """Lowercase scheme+host, strip trailing slash. Both sides of allowlist
    comparison go through this so AUTH_URL=`https://Example.com/` matches
    ALLOWED_ORIGINS=`https://example.com`."""
    return value.strip().rstrip("/").lower()


class OriginAllowlistMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_origins: list[str]) -> None:
        super().__init__(app)
        self._allowed = {_normalize_origin(o) for o in allowed_origins}

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in _MUTATING_METHODS:
            if request.url.path.startswith(_INTERNAL_BYPASS_PREFIX):
                provided = request.headers.get("x-internal-secret", "")
                expected = get_settings().internal_api_secret
                if provided and hmac.compare_digest(provided, expected):
                    return await call_next(request)
            origin = request.headers.get("origin")
            if origin and _normalize_origin(origin) in self._allowed:
                return await call_next(request)
            # Some clients strip Origin on same-origin POST; fall back to Referer.
            referer = request.headers.get("referer")
            if referer:
                parsed = urlparse(referer)
                referer_origin = f"{parsed.scheme}://{parsed.netloc}"
                if _normalize_origin(referer_origin) in self._allowed:
                    return await call_next(request)
            _log.warning(
                "csrf_mismatch", extra={"origin": origin, "referer": referer}
            )
            return JSONResponse({"detail": "csrf_mismatch"}, status_code=403)
        return await call_next(request)
