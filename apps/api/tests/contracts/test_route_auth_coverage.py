"""Every /v1 route carries an auth dependency, or is on the open allowlist.

``GET /v1/words/search`` was once the only business route with no auth dependency
at all — no ``current_user``, no ``optional_current_user``, and no global default
to fall back on. It was not a policy decision, it was an omission, and nothing in
the suite could tell the difference. This enumerates the live app instead of a
file, so a new route lands in the allowlist deliberately or fails here.

Note what this does NOT assert: that a route is *sign-in only*. Anonymous read of
public content is intended (a shared deck opens from its own link), so
``optional_current_user`` counts as covered. What is forbidden is a route with no
identity boundary whatsoever.

Coverage is by construction, not by enumeration: the loop walks
``create_app().routes``, so every module mounted on the app is included the moment
it is mounted — currently 42 routes across assistant, content, hierarchy,
learning, realtime and sessions. There is no per-module list to keep in sync,
which is the failure mode this file exists to avoid.

Verified to fail: removing ``Depends(current_user)`` from one learning route makes
this red naming that exact path, and restoring it makes it green. A guard nobody
has watched fail is not a guard.
"""

from pycil.auth.deps import current_user, optional_current_user
from pycil.main import create_app

# Unauthenticated by design. Each is a fact about the deployment rather than about
# a learner, and none reads or writes owned data.
OPEN_PATHS = {
    "/v1/capabilities",
    "/v1/openapi.json",
    "/health",
    "/health/live",
    "/health/ready",
}

# Login cannot require the credential it issues.
AUTH_HANDSHAKE_PATHS = {
    "/v1/auth/login",
    "/v1/auth/callback",
}

_ACCEPTED = {current_user, optional_current_user}


def _guards(route) -> set:
    """Every callable reachable as a dependency of this route, one level deep."""
    found = set()
    for dependency in getattr(route.dependant, "dependencies", []):
        found.add(dependency.call)
        for nested in getattr(dependency, "dependencies", []):
            found.add(nested.call)
    return found


def test_every_v1_route_has_an_identity_boundary():
    unguarded = []
    for route in create_app().routes:
        path = getattr(route, "path", "")
        if not path.startswith("/v1"):
            continue
        if path in OPEN_PATHS or path in AUTH_HANDSHAKE_PATHS:
            continue
        if not _guards(route) & _ACCEPTED:
            unguarded.append(f"{sorted(route.methods)} {path}")

    assert not unguarded, (
        "these /v1 routes have no auth dependency; add one or justify it in "
        f"OPEN_PATHS: {unguarded}"
    )


def test_the_allowlisted_paths_still_exist():
    """A stale allowlist entry silently exempts nothing and hides the next omission."""
    live = {getattr(route, "path", "") for route in create_app().routes}
    missing = (OPEN_PATHS | AUTH_HANDSHAKE_PATHS) - live
    assert not missing, f"allowlist names routes that no longer exist: {missing}"


def test_word_search_is_covered_by_the_boundary():
    """The route this guard was written for, asserted by name.

    Kept explicit so the reason for the file survives a refactor of the loop above.
    """
    search = [
        route
        for route in create_app().routes
        if getattr(route, "path", "") == "/v1/words/search"
    ]
    assert len(search) == 1
    assert optional_current_user in _guards(search[0])
