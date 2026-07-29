"""Extract the API's error codes from source into a TypeScript fixture.

The web taxonomy was previously hand-enumerated and had already drifted: four
reachable codes had no entry. Reading the raise sites directly is the only way
the two stay in step, because a new `raise ConflictError("...")` is otherwise
invisible to the frontend until someone hits it.

Run from apps/api:  uv run python scripts/extract-error-codes.py
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = API_ROOT / "pycil"
OUT_FILE = API_ROOT.parent / "web" / "lib" / "api" / "error-codes.generated.ts"

# Mirrors `_CODE_SHAPED` in pycil/common/errors.py. A message matching this
# becomes the wire code, so the same test decides what is extractable here.
CODE_SHAPED = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")

# status_code per error class, read off pycil/common/errors.py. A code can be
# raised from more than one class, so the status is a set per code rather than a
# single value.
ERROR_STATUS = {
    "AppError": 400,
    "NotFoundError": 404,
    "ForbiddenError": 403,
    "UnauthorizedError": 401,
    "ConflictError": 409,
    "ServiceUnavailableError": 503,
    "TooManyRequestsError": 429,
}

# Handler-minted codes that no domain raise site produces. `app_error_handler`
# and its siblings in pycil/common/errors.py emit these directly, and the
# middleware adds its own, so walking raise statements cannot find them.
HANDLER_CODES = {
    "validation_error": 422,
    "http_error": 400,
    "method_not_allowed": 405,
    "payload_too_large": 413,
    # Class defaults, still reachable: a prose or interpolated message does not
    # become a code, so the raise falls back to its class default.
    "bad_request": 400,
    "not_found": 404,
    "forbidden": 403,
    "unauthorized": 401,
    "conflict": 409,
    "service_unavailable": 503,
    "too_many_requests": 429,
}


def literal(node: ast.expr | None) -> str | None:
    """The value of a plain string literal, or None for anything else.

    An f-string or a variable is deliberately not resolved: at runtime it will
    not match `_CODE_SHAPED` either, so it is not a code.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def collect() -> dict[str, set[int]]:
    """Every code the API can emit, mapped to the statuses it can carry."""
    codes: dict[str, set[int]] = {}

    for code, status in HANDLER_CODES.items():
        codes.setdefault(code, set()).add(status)

    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            func = node.exc.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            status = ERROR_STATUS.get(name or "")
            if status is None:
                continue

            # An explicit code= wins, exactly as the constructor decides.
            explicit = next(
                (literal(kw.value) for kw in node.exc.keywords if kw.arg == "code"),
                None,
            )
            if explicit:
                codes.setdefault(explicit, set()).add(status)
                continue

            message = literal(node.exc.args[0]) if node.exc.args else None
            if message and CODE_SHAPED.fullmatch(message):
                codes.setdefault(message, set()).add(status)

    return codes


def render(codes: dict[str, set[int]], revision: str) -> str:
    entries = "\n".join(
        f"  {code!r}: [{', '.join(str(s) for s in sorted(statuses))}],".replace("'", '"')
        for code, statuses in sorted(codes.items())
    )
    return f"""/**
 * Generated from apps/api by scripts/extract-error-codes.py. Do not edit.
 *
 * Source revision: {revision}
 *
 * Every error code the API can put on the wire, with the HTTP statuses it can
 * arrive with. A code appears under more than one status when it is raised from
 * more than one error class.
 *
 * Regenerate with:  cd apps/api && uv run python scripts/extract-error-codes.py
 */

export const API_ERROR_STATUS = {{
{entries}
}} as const

export type ApiErrorCode = keyof typeof API_ERROR_STATUS

export const API_ERROR_CODES = Object.keys(API_ERROR_STATUS) as ApiErrorCode[]

/** Whether a code from a response is one this build knows about. */
export function isKnownApiErrorCode(code: string): code is ApiErrorCode {{
  return code in API_ERROR_STATUS
}}
"""


def main() -> int:
    codes = collect()
    if len(codes) < 50:
        # A parse or path regression would silently emit a near-empty table, and
        # the taxonomy test would then pass by having nothing to check.
        print(f"only {len(codes)} codes found; expected the full surface", file=sys.stderr)
        return 1

    revision = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        cwd=API_ROOT,
        check=False,
    ).stdout.strip()

    OUT_FILE.write_text(render(codes, revision or "unknown"), encoding="utf-8")
    print(f"wrote {len(codes)} codes to {OUT_FILE.relative_to(API_ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
