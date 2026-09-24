"""Every error code the API can emit must be one the web client knows.

The two halves of this repository are written in different languages and share no
type system, so an error code added, renamed or retired on the server leaves
`apps/web/lib/api/error-codes.ts` quietly stale. Nothing else catches it: `tsc` has
no idea what the API raises, and the API's tests never read the web sources. The
failure is silent in the worst way — `classifyErrorCode` returns its generic
fallback for a code it does not know, so a genuinely retryable failure renders
"something went wrong" and offers no retry.

That is not hypothetical. The map had drifted in both directions: 27 codes the API
raises were absent (including every Clerk identity failure and the whole study
session recovery set), 16 entries named codes the API had stopped raising at all —
the retired OAuth and refresh-token set — and `assistant_message_too_long` carried
the wrong status. The web also branched on `answer_grading_quota_exceeded` in two
places, a code no API version in this repository raises.

This reads the *server's* raise sites and checks them against the *client's* map,
because the server is the authority and the client is the thing that drifts. Both
directions are asserted: a missing code makes a real failure unreadable, and an
entry for a code nothing raises is a claim the client handles something it never
sees — which is what let the dead quota branch survive review.

The check is static, on the constructs that actually produce a wire code: raise
sites of the error classes, their class-level defaults, and the codes the HTTP
handlers and middleware synthesize. A code mentioned in a comment or a docstring is
documentation, not a response.
"""

import ast
import pathlib
import re

import pytest

from pycil.common.errors import AppError

REPO = pathlib.Path(__file__).resolve().parents[5]
API = REPO / "apps" / "api" / "pycil"
WEB_CODES = REPO / "apps" / "web" / "lib" / "api" / "error-codes.ts"

#: A snake_case identifier, which is what `AppError.__init__` promotes to the wire
#: code. Prose fails this — it has spaces, punctuation, or interpolated values.
_CODE_SHAPED = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")

#: `"code": [401]` inside the web's status map.
_WEB_ENTRY = re.compile(r'"([a-z0-9_]+)":\s*\[([\d,\s]+)\]')


def _error_classes() -> dict[str, tuple[str, int]]:
    """Every `AppError` subclass, as name -> (default code, default status).

    The class attributes are the fallback, but a subclass may set its code from its
    own `__init__` instead of a class attribute — `CreditExhaustedError` does
    exactly that. So each class is instantiated with no arguments where it can be,
    which reads the code the constructor actually produces rather than the one the
    class body happens to declare.
    """
    found: dict[str, tuple[str, int]] = {}

    def walk(cls: type) -> None:
        try:
            instance = cls()
        except TypeError:
            # Needs arguments; its class attributes are the best available answer.
            found[cls.__name__] = (cls.code, cls.status_code)
        else:
            found[cls.__name__] = (instance.code, instance.status_code)
        for sub in cls.__subclasses__():
            walk(sub)

    walk(AppError)
    return found


def _raise_sites(classes: dict[str, tuple[str, int]]) -> dict[str, set[int]]:
    """Codes raised explicitly, with the status each arrives under.

    A raise site names a code either as a snake_case positional message, which
    `AppError.__init__` promotes, or as an explicit `code=` keyword.
    """
    codes: dict[str, set[int]] = {}
    for source in sorted(API.rglob("*.py")):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name not in classes:
                continue
            _, status = classes[name]
            code = None
            if (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and _CODE_SHAPED.fullmatch(node.args[0].value)
            ):
                code = node.args[0].value
            for keyword in node.keywords:
                if keyword.arg == "code" and isinstance(keyword.value, ast.Constant):
                    code = keyword.value.value
            if code:
                codes.setdefault(code, set()).add(status)
    return codes


def _http_exception_handler_codes() -> dict[str, set[int]]:
    """What `http_error_handler` can emit, from its table and this codebase's raises.

    The handler maps a status onto a code and falls back to `http_error` for
    anything unlisted. The table alone would miss `http_error`; the fallback alone
    would invent a status. So the fallback's statuses come from the
    `raise HTTPException(...)` sites in this codebase.

    Starlette's own raises are deliberately not scanned. It raises 404 and 405 from
    routing, which the table already maps, and 400 from form parsing, which nothing
    here uses — including them would assert a status this API cannot produce and
    make the check depend on framework internals rather than on this codebase.
    """
    tables: dict[str, dict[int, str]] = {}
    for source in sorted(API.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                target = node.targets[0]
                name = target.id if isinstance(target, ast.Name) else None
                if not name:
                    continue
                entries = {
                    key.value: value.value
                    for key, value in zip(node.value.keys, node.value.values, strict=True)
                    if isinstance(key, ast.Constant)
                    and isinstance(key.value, int)
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                }
                if entries:
                    tables[name] = entries

    codes: dict[str, set[int]] = {}
    for table in tables.values():
        for status, code in table.items():
            codes.setdefault(code, set()).add(status)

    # The handler the table belongs to, found by the table it consults.
    handler_table = next((t for t in tables.values() if "unauthorized" in t.values()), {})

    for source in sorted(API.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            func = node.exc.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name != "HTTPException":
                continue
            status = node.exc.args[0] if node.exc.args else None
            if status is None:
                status = next(
                    (
                        kw.value
                        for kw in node.exc.keywords
                        if kw.arg == "status_code" and isinstance(kw.value, ast.Constant)
                    ),
                    None,
                )
            if isinstance(status, ast.Constant) and isinstance(status.value, int):
                codes.setdefault(handler_table.get(status.value, "http_error"), set()).add(
                    status.value
                )
    return codes


def _synthesized_codes() -> dict[str, set[int]]:
    """Codes the handlers and middleware produce without raising an error class.

    Neither `error_envelope(... code=...)` nor the body-size middleware's
    hand-written envelope goes through `AppError`, so neither is visible to a scan
    of raise sites.
    """
    codes: dict[str, set[int]] = _http_exception_handler_codes()

    for source in sorted(API.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if name == "error_envelope":
                    named = {
                        kw.arg: kw.value.value
                        for kw in node.keywords
                        if kw.arg in {"code", "status"} and isinstance(kw.value, ast.Constant)
                    }
                    if isinstance(named.get("code"), str) and isinstance(named.get("status"), int):
                        codes.setdefault(named["code"], set()).add(named["status"])
                elif name == "_middleware_error" and len(node.args) >= 3:
                    status, code = node.args[1], node.args[2]
                    if (
                        isinstance(status, ast.Constant)
                        and isinstance(status.value, int)
                        and isinstance(code, ast.Constant)
                        and isinstance(code.value, str)
                    ):
                        codes.setdefault(code.value, set()).add(status.value)

            if isinstance(node, ast.Dict):
                entries = {
                    key.value: value.value
                    for key, value in zip(node.keys, node.values, strict=True)
                    if isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and isinstance(value, ast.Constant)
                }
                # `{"status": 413, "code": "payload_too_large"}` — one envelope.
                status, code = entries.get("status"), entries.get("code")
                if isinstance(status, int) and isinstance(code, str):
                    codes.setdefault(code, set()).add(status)
    return codes


def _api_codes() -> dict[str, set[int]]:
    """Every code the API can put on the wire, with its possible statuses."""
    classes = _error_classes()
    codes = {code: {status} for code, status in classes.values()}
    for source in (_raise_sites(classes), _synthesized_codes()):
        for code, statuses in source.items():
            codes.setdefault(code, set()).update(statuses)
    return codes


def _web_codes() -> dict[str, set[int]]:
    """The client's hand-maintained map."""
    text = WEB_CODES.read_text(encoding="utf-8")
    return {
        match.group(1): {int(n) for n in re.findall(r"\d+", match.group(2))}
        for match in _WEB_ENTRY.finditer(text)
    }


def test_the_extraction_actually_reads_the_sources():
    """Guard the check itself: a broken parser would make both assertions vacuous."""
    assert API.is_dir(), f"API package not found at {API}"
    assert WEB_CODES.is_file(), f"web error-code map not found at {WEB_CODES}"
    api, web = _api_codes(), _web_codes()
    assert len(api) >= 50, f"only {len(api)} API codes extracted; the scan is broken"
    assert len(web) >= 50, f"only {len(web)} web codes parsed; the map is broken"
    # Codes from each of the three extraction paths, so none can silently no-op.
    assert "session_scope_changed" in api, "raise-site scan found nothing"
    assert "not_found" in api, "class-default scan found nothing"
    assert "validation_error" in api, "handler-synthesized scan found nothing"


def test_every_code_the_api_raises_is_known_to_the_web_client():
    missing = {
        code: sorted(statuses)
        for code, statuses in _api_codes().items()
        if code not in _web_codes()
    }
    if missing:
        detail = "\n".join(f"  {code}  {statuses}" for code, statuses in sorted(missing.items()))
        pytest.fail(
            "The API raises codes the web client does not know. Each one reaches "
            "`classifyErrorCode`, falls through to the generic fallback, and renders "
            "'something went wrong' with no retry — so a recoverable failure looks "
            "like a broken product:\n" + detail
        )


def test_the_web_client_claims_no_code_the_api_cannot_send():
    extra = {
        code: sorted(statuses)
        for code, statuses in _web_codes().items()
        if code not in _api_codes()
    }
    if extra:
        detail = "\n".join(f"  {code}  {statuses}" for code, statuses in sorted(extra.items()))
        pytest.fail(
            "The web client maps codes the API never sends. An entry for a code "
            "nothing raises is a claim the client handles a failure it never sees, "
            "and it is what lets a dead branch survive review — the client was still "
            "branching on a grading quota the API had already removed:\n" + detail
        )


def test_the_statuses_agree():
    api, web = _api_codes(), _web_codes()
    disagreements = {
        code: (sorted(api[code]), sorted(web[code]))
        for code in api.keys() & web.keys()
        if not api[code] <= web[code]
    }
    if disagreements:
        detail = "\n".join(
            f"  {code}  api={api_statuses} web={web_statuses}"
            for code, (api_statuses, web_statuses) in sorted(disagreements.items())
        )
        pytest.fail(
            "The API can send these codes under a status the web client does not "
            "associate with them, so a status-based decision reads the wrong case:\n"
            + detail
        )


def test_a_code_that_used_to_drift_is_now_covered():
    """Proves the check against a real case, not just a count."""
    api, web = _api_codes(), _web_codes()
    # Absent from the map entirely before this check existed.
    assert "identity_conflict" in api and "identity_conflict" in web
    assert "study_session_changed" in api and "study_session_changed" in web
    # Carried the wrong status before: raised as 413, mapped as 503.
    assert api["assistant_message_too_long"] <= web["assistant_message_too_long"]
    # Retired with the custom OAuth flow, and still mapped.
    assert "oauth_exchange_failed" not in api and "oauth_exchange_failed" not in web
