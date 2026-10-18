"""Bounded read-only release checks; bearer token arrives on stdin, never argv."""

import json
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import UUID

base = sys.argv[1].rstrip("/")
authenticated = sys.argv[2] == "authenticated"
token = sys.stdin.read().strip()
if (authenticated and not token) or "\n" in token or "\r" in token:
    raise SystemExit("smoke: a current operator test-session token is required")
try:
    paths = ["/readyz", "/v1/words:search?query=hello&include_reference=true"]
    if token:
        paths.append("/v1/me")
    for path in paths:
        headers = {"User-Agent": "pycil-deployment/1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(base + path, headers=headers)
        with urlopen(request, timeout=5) as response:
            body = json.load(response)
            if path == "/readyz":
                assert body.get("status") == "ready"
            elif path.startswith("/v1/words:search"):
                assert isinstance(body.get("items"), list) and body["items"]
            else:
                UUID(body["id"])
except (
    OSError,
    URLError,
    ValueError,
    AssertionError,
    AttributeError,
    KeyError,
    TypeError,
):
    raise SystemExit(
        "smoke: readiness, reference search or authenticated account check failed"
    ) from None
print(
    "smoke: ready and reference search passed"
    + ("; authenticated account passed" if token else "")
)
