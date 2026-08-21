"""Every ``pycil/*/router.py`` holds routes, and nothing else.

Routers grew services, raw SQL, and helper colonies because "routes only" was a
prose rule, and prose does not survive "just one" helper. These assertions are
mechanical instead: line budgets, no query construction, no private helpers
beyond a documented allow-list, no function-local imports, and a floor on
registered routes so a split cannot quietly drop an endpoint.

The allow-lists are the honest exception, not the rule: an allowed helper must
be pure HTTP-layer glue (framing, header parsing, DTO projection) with no I/O
and no state transitions. Anything that touches the database or orchestrates a
workflow belongs in the application layer, allow-list or not.
"""

import ast
import pathlib

import pytest

PYCIL = pathlib.Path(__file__).resolve().parents[2] / "pycil"

# Measured after the assistant and content extractions, with headroom for about
# one more route each. Not a style preference: past the budget, the file is
# holding something that is not a route again.
CONTRACTS = {
    "account_lifecycle": {"max_lines": 80, "routes": 2},
    "assistant": {
        "max_lines": 280,
        "routes": 7,
        # SSE framing and request glue for the streaming endpoints: frame
        # encoding, heartbeat wrapping, graph lookup, Last-Event-ID parsing.
        # Pure wire mechanics — no queries, no state transitions.
        "allowed_private_helpers": {
            "_event_frame",
            "_framed",
            "_graph",
            "_stream",
            "_last_event_id",
        },
    },
    "auth": {"max_lines": 200, "routes": 4},
    "content": {
        "max_lines": 290,
        "routes": 6,
        # Projections of a Lexi sense view onto the response DTOs. Pure
        # functions over data the route already authorized and fetched.
        "allowed_private_helpers": {"_sense_content", "_sense_detail"},
    },
    "hierarchy": {"max_lines": 340, "routes": 14},
    "learning": {"max_lines": 340, "routes": 8},
    "realtime": {"max_lines": 90, "routes": 2},
}

_HTTP_METHODS = {"get", "post", "patch", "put", "delete"}


def _router_path(package: str) -> pathlib.Path:
    return PYCIL / package / "router.py"


def _tree(package: str) -> ast.Module:
    path = _router_path(package)
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_every_router_module_is_under_contract():
    """A new ``router.py`` without a contract entry would ship unguarded."""
    discovered = {path.parent.name for path in PYCIL.glob("*/router.py")}
    assert discovered == set(CONTRACTS), (
        f"router modules and contracts drifted apart: "
        f"uncontracted {sorted(discovered - set(CONTRACTS))}, "
        f"stale entries {sorted(set(CONTRACTS) - discovered)}"
    )


@pytest.mark.parametrize("package", sorted(CONTRACTS))
def test_the_router_stays_small_enough_to_read(package: str) -> None:
    lines = len(_router_path(package).read_text(encoding="utf-8").splitlines())
    limit = CONTRACTS[package]["max_lines"]
    assert lines <= limit, (
        f"{package}/router.py is {lines} lines (limit {limit}). "
        "Read helpers belong in the application reads module; mutations in the "
        "application service."
    )


@pytest.mark.parametrize("package", sorted(CONTRACTS))
def test_the_router_builds_no_queries(package: str) -> None:
    """A `select(...)` or `text(...)` here is a read that skipped its own layer."""
    offenders = []
    for node in ast.walk(_tree(package)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"select", "text"}:
                offenders.append(f"{node.func.id}() at line {node.lineno}")
    assert not offenders, f"raw query construction in {package}/router.py: {offenders}"


@pytest.mark.parametrize("package", sorted(CONTRACTS))
def test_the_router_defines_no_private_helpers(package: str) -> None:
    """A module-level private in a router is a service that has not moved yet."""
    allowed = CONTRACTS[package].get("allowed_private_helpers", set())
    offenders = [
        node.name
        for node in _tree(package).body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("_")
        and node.name not in allowed
    ]
    assert not offenders, f"private helpers still in {package}/router.py: {offenders}"


@pytest.mark.parametrize("package", sorted(CONTRACTS))
def test_the_router_has_no_function_local_imports(package: str) -> None:
    """A deferred import usually hides a cycle; the cycle is the thing to fix."""
    offenders = set()
    for parent in ast.walk(_tree(package)):
        if not isinstance(parent, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for node in ast.walk(parent):
            if isinstance(node, ast.Import | ast.ImportFrom):
                offenders.add(f"{parent.name} (line {node.lineno})")
    assert not offenders, f"function-local imports in {package}/router.py: {sorted(offenders)}"


@pytest.mark.parametrize("package", sorted(CONTRACTS))
def test_routes_survive(package: str) -> None:
    """Guard against a split having quietly dropped an endpoint.

    Counted from the decorators rather than hardcoded per path, so adding a route
    does not fail this — only losing one below the count the contract started
    with.
    """
    floor = CONTRACTS[package]["routes"]
    routes = [
        node
        for node in _tree(package).body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and any(
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and dec.func.attr in _HTTP_METHODS
            for dec in node.decorator_list
        )
    ]
    assert len(routes) >= floor, f"only {len(routes)} routes survive in {package}/router.py"
