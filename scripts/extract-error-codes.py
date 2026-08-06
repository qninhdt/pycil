#!/usr/bin/env python3
"""Extract every error code the API can put on the wire into a TypeScript map.

The web client branches on `error.code`, and its `ERROR_TAXONOMY` is typed
`Record<ApiErrorCode, ...>` keyed off the file this writes. So a code added on the
Python side does not merely go undocumented — the taxonomy silently lacks an
entry, `typecheck` stays green because the key set never changed, and the UI falls
through to a generic message for a case someone deliberately gave a code to.

The generated file existed already and named this script in its header, but the
script itself was never committed: nothing regenerated or verified it. Measured at
the time of writing, three codes the API raises were absent from it, including one
added the same day.

Run from `apps/api`:
    uv run python ../../scripts/extract-error-codes.py

CI runs it and fails when the working tree is dirty afterwards, which turns "the
generated file is stale" from something nobody notices into a red build.

Codes come from three places, all of which have to be read to be correct:

1. Explicit raises — `ConflictError("session_scope_changed")`. The message IS the
   code (see `AppError.__init__`: a snake_case message is promoted to `code`).
2. Class defaults — `NotFoundError.code = "not_found"`, used whenever a raise
   passes human prose instead of an identifier.
3. Literals passed as `code=` and the codes middleware emits before any route
   runs, which no raise site mentions.
"""

from __future__ import annotations

import ast
import pathlib
import re
import subprocess
import sys

API_ROOT = pathlib.Path(__file__).resolve().parent.parent / "apps" / "api"
PACKAGE = API_ROOT / "pycil"
ERRORS_MODULE = PACKAGE / "common" / "errors.py"
OUTPUT = (
    pathlib.Path(__file__).resolve().parent.parent
    / "apps"
    / "web"
    / "lib"
    / "api"
    / "error-codes.generated.ts"
)

# Same shape `AppError.__init__` uses to decide a message is really an identifier.
CODE_SHAPED = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")


def error_classes() -> dict[str, tuple[int, str]]:
    """`{class_name: (status_code, default_code)}` for every AppError subclass.

    Read out of the AST rather than by importing, so this script has no
    dependency on the app's settings or database being available.
    """
    tree = ast.parse(ERRORS_MODULE.read_text(encoding="utf-8"))
    classes: dict[str, tuple[int, str]] = {}

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
        if node.name != "AppError" and not bases & {"AppError", *classes}:
            continue

        status, code = None, None
        for stmt in node.body:
            target = None
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                target, value = stmt.target.id, stmt.value
            elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                if isinstance(stmt.targets[0], ast.Name):
                    target, value = stmt.targets[0].id, stmt.value
            if target == "status_code" and isinstance(value, ast.Constant):
                status = value.value
            elif target == "code" and isinstance(value, ast.Constant):
                code = value.value

        inherited = classes.get(next(iter(bases & classes.keys()), ""), (400, "bad_request"))
        classes[node.name] = (status or inherited[0], code or inherited[1])

    return classes


def scan_raises(classes: dict[str, tuple[int, str]]) -> dict[str, set[int]]:
    """Every `(code -> statuses)` pair reachable from a raise of a known class."""
    found: dict[str, set[int]] = {}

    def record(code: str, status: int) -> None:
        found.setdefault(code, set()).add(status)

    for source in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in str(source):
            continue
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except SyntaxError as exc:
            print(f"error: cannot parse {source}: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            cls = node.func.id
            if cls not in classes:
                continue
            status, default = classes[cls]

            explicit = next(
                (
                    kw.value.value
                    for kw in node.keywords
                    if kw.arg == "code" and isinstance(kw.value, ast.Constant)
                ),
                None,
            )
            if explicit:
                record(explicit, status)
                continue

            # A positional message that reads as an identifier IS the code.
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                if CODE_SHAPED.fullmatch(first.value):
                    record(first.value, status)
                    continue
            record(default, status)

    return found


def scan_envelope_literals() -> dict[str, set[int]]:
    """Codes emitted outside a raise: handlers and middleware.

    These never appear as an exception class, so a raise-only scan misses them —
    and they are the codes a client is most likely to hit on a bad request, before
    any route runs.

    The status is looked for across the whole enclosing statement rather than as a
    sibling keyword. `validation_error_handler` puts `status_code=422` on the
    `JSONResponse` while `code=` sits on a nested `error_envelope(...)` call, and
    the body-limit middleware expresses its status as `"status": 413` inside a
    dict. Reading only sibling kwargs attributed both to 500.
    """
    found: dict[str, set[int]] = {}
    for name in ("common/errors.py", "common/middleware.py"):
        source = PACKAGE / name
        if not source.exists():
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for stmt in ast.walk(tree):
            if not isinstance(stmt, ast.stmt):
                continue
            codes_here: set[str] = set()
            statuses_here: set[int] = set()
            for node in ast.walk(stmt):
                if isinstance(node, ast.keyword) and isinstance(node.value, ast.Constant):
                    if node.arg == "code" and isinstance(node.value.value, str):
                        if CODE_SHAPED.fullmatch(node.value.value):
                            codes_here.add(node.value.value)
                    elif node.arg == "status_code" and isinstance(node.value.value, int):
                        statuses_here.add(node.value.value)
                # `{"status": 413}` — how the middleware carries its status.
                if isinstance(node, ast.Dict):
                    for key, value in zip(node.keys, node.values, strict=False):
                        if (
                            isinstance(key, ast.Constant)
                            and key.value == "status"
                            and isinstance(value, ast.Constant)
                            and isinstance(value.value, int)
                        ):
                            statuses_here.add(value.value)
            for code in codes_here:
                # An unlocatable status is reported as 500 rather than dropped: a
                # code the client can receive must appear in the map either way.
                found.setdefault(code, set()).update(statuses_here or {500})

    # The status-keyed table in `http_error_handler` maps a bare HTTPException onto
    # a code. Those are reachable from any route, so they belong in the map.
    for code, status in (
        ("unauthorized", 401),
        ("forbidden", 403),
        ("not_found", 404),
        ("method_not_allowed", 405),
        ("http_error", 500),
    ):
        found.setdefault(code, set()).add(status)
    return found


def source_revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True, cwd=API_ROOT,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def render(codes: dict[str, set[int]]) -> str:
    lines = [
        "/**",
        " * Generated from apps/api by scripts/extract-error-codes.py. Do not edit.",
        " *",
        f" * Source revision: {source_revision()}",
        " *",
        " * Every error code the API can put on the wire, with the HTTP statuses it can",
        " * arrive with. A code appears under more than one status when it is raised from",
        " * more than one error class.",
        " *",
        " * Regenerate with:  cd apps/api && uv run python ../../scripts/extract-error-codes.py",
        " */",
        "",
        "export const API_ERROR_STATUS = {",
    ]
    for code in sorted(codes):
        statuses = ", ".join(str(s) for s in sorted(codes[code]))
        lines.append(f'  "{code}": [{statuses}],')
    lines += [
        "} as const",
        "",
        "export type ApiErrorCode = keyof typeof API_ERROR_STATUS",
        "",
        "export const API_ERROR_CODES = Object.keys(API_ERROR_STATUS) as ApiErrorCode[]",
        "",
        "export function isKnownApiErrorCode(code: string): code is ApiErrorCode {",
        "  return code in API_ERROR_STATUS",
        "}",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    classes = error_classes()
    if not classes:
        print("error: no AppError subclasses found — did errors.py move?", file=sys.stderr)
        return 2

    codes = scan_raises(classes)
    for code, statuses in scan_envelope_literals().items():
        codes.setdefault(code, set()).update(statuses)

    # Every class default is reachable: any raise passing human prose instead of an
    # identifier falls back to it, and `AppError.__init__` does that silently. They
    # were dropped when only literal raise arguments were scanned, which removed
    # `bad_request`, `conflict`, `service_unavailable` and `too_many_requests` from
    # a file whose whole job is to be exhaustive.
    for status, default in classes.values():
        codes.setdefault(default, set()).add(status)

    OUTPUT.write_text(render(codes), encoding="utf-8")
    print(f"wrote {len(codes)} error codes to {OUTPUT.relative_to(OUTPUT.parents[4])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
