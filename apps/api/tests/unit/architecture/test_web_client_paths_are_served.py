"""Every path the web client fetches must exist in the API's own OpenAPI document.

The two halves of this repository are written in different languages and share no
type system, so a route rename on the server and a stale path on the client compile
and typecheck cleanly on both sides. Nothing else catches it: `tsc` has no idea what
the API serves, and the API's tests never read the web sources. The failure surfaces
as a 404 in a live page.

That is not hypothetical. The analytics routes were consolidated onto `/v1/me/*`
with an optional `nodeId` scope, and `lib/api/resources/analytics.ts` kept calling
`/v1/folders/{id}/stats`, `/weakest`, `/cefr` and `/history` — four endpoints that
had stopped existing. The progress page's folder scope was broken while every suite
stayed green.

This reads the *client's* source and checks it against the *server's* generated
schema, because the schema is the authority and the client is the thing that drifts.
It is a static check on `fetch<T>(...)` call sites only: a path mentioned in a
comment is documentation, not a request.
"""

import pathlib
import re

import pytest

from pycil.main import create_app

REPO = pathlib.Path(__file__).resolve().parents[5]
RESOURCES = REPO / "apps" / "web" / "lib" / "api" / "resources"

#: `fetch<Type>(`path`)` — the only shape that issues a request.
_CALL = re.compile(r"fetch<[^>]*>\(\s*[`\"](/v1/[^`\"]*)[`\"]")

#: A trailing `${queryString({...})}`; its argument braces nest, so it cannot be
#: handled by the generic interpolation rule below.
_QUERY_STRING = re.compile(r"\$\{queryString\(.*?\)\}")

#: Any remaining `${...}` interpolation, e.g. `/v1/nodes/${nodeId}`.
_INTERPOLATION = re.compile(r"\$\{[^}]*\}")


def _served_paths() -> set[str]:
    """The API's paths with every parameter normalised to `{}`."""
    return {
        re.sub(r"\{[^}]+\}", "{}", path) for path in create_app().openapi()["paths"]
    }


def _fetched_paths() -> dict[str, str]:
    """Every path the web resources fetch, mapped to the file that fetches it."""
    found: dict[str, str] = {}
    for source in sorted(RESOURCES.glob("*.ts")):
        for match in _CALL.finditer(source.read_text(encoding="utf-8")):
            raw = _QUERY_STRING.sub("", match.group(1)).split("?")[0]
            found.setdefault(_INTERPOLATION.sub("{}", raw), source.name)
    return found


def test_the_web_resources_directory_is_where_this_test_thinks_it_is():
    """Guard the check itself: an empty glob would make the assertion vacuous."""
    assert RESOURCES.is_dir(), f"web API resources not found at {RESOURCES}"
    assert list(RESOURCES.glob("*.ts")), "no resource modules to check"


def test_every_path_the_web_client_fetches_is_served():
    served = _served_paths()
    missing = {
        path: source
        for path, source in _fetched_paths().items()
        if path not in served
    }
    if missing:
        detail = "\n".join(f"  {path}  ({source})" for path, source in sorted(missing.items()))
        pytest.fail(
            "The web client fetches paths the API does not serve. Either the route "
            "was renamed and the client was not updated, or the client is calling a "
            "route that was never built:\n" + detail
        )


def test_the_check_actually_reads_a_meaningful_number_of_calls():
    """A parsing change that stopped matching would otherwise pass silently."""
    fetched = _fetched_paths()
    assert len(fetched) >= 20, (
        f"only {len(fetched)} fetch calls parsed; the matcher has probably stopped "
        "recognising the call shape rather than the client having shrunk"
    )


def test_a_known_good_path_is_recognised():
    """Proves the matcher against a real call site, not just a count."""
    assert "/v1/me/stats" in _fetched_paths()


def test_the_served_paths_are_read_from_the_live_schema():
    """The comparison's right-hand side must come from the app, not a fixture."""
    served = _served_paths()
    assert "/v1/me/stats" in served
    assert "/v1/folders/{}/items" in served
    # The consolidated analytics routes: a folder scope is a parameter, not a path.
    assert "/v1/folders/{}/stats" not in served
