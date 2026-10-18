"""Mint a fresh smoke token for an existing Clerk session; stdout is a private pipe."""

import json
import re
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from compose import read_environment

try:
    key = read_environment(Path(sys.argv[1]))["CLERK_SECRET_KEY"]
    session = Path(sys.argv[2]).read_text().strip()
    if not re.fullmatch(r"sess_[A-Za-z0-9]+", session):
        raise ValueError("Invalid session")
    request = Request(
        f"https://api.clerk.com/v1/sessions/{session}/tokens",
        data=b"{}",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "pycil-deployment/1.0",
        },
    )
    with urlopen(request, timeout=10) as response:
        token = json.load(response)["jwt"]
    if not isinstance(token, str) or not token or any(c.isspace() for c in token):
        raise ValueError("Invalid token")
except (OSError, URLError, ValueError, KeyError, TypeError):
    raise SystemExit(
        "smoke: cannot mint a token; verify the dedicated Clerk session"
    ) from None
print(token)
