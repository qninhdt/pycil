"""`hierarchy/router.py` holds routes, and nothing else.

It was 553 lines: 14 routes, 7 private helpers that were really services, three
raw SQL blocks, and a function-local import. All read traffic lived here while
`service.py` owned only mutations, so reads had no layer of their own and bypassed
the service boundary entirely.

The helpers moved to `reads.py` and the cached subtree read to `subtree.py`. These
assertions are mechanical because the prose version ("routes only") is not
checkable and would rot the first time someone added "just one" helper back.
"""

import ast
import pathlib

ROUTER = pathlib.Path(__file__).resolve().parents[2] / "pycil" / "hierarchy" / "router.py"

# Measured after the extraction, with headroom for a route or two. Not a style
# preference: past this, the file is holding something that is not a route again.
MAX_LINES = 340


def _tree() -> ast.Module:
    return ast.parse(ROUTER.read_text(encoding="utf-8"), filename=str(ROUTER))


def test_the_router_stays_small_enough_to_read():
    lines = len(ROUTER.read_text(encoding="utf-8").splitlines())
    assert lines <= MAX_LINES, (
        f"hierarchy/router.py is {lines} lines (limit {MAX_LINES}). "
        "Read helpers belong in reads.py; mutations in service.py."
    )


def test_the_router_builds_no_queries():
    """A `select(...)` or `text(...)` here is a read that skipped its own layer."""
    offenders = []
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"select", "text"}:
                offenders.append(f"{node.func.id}() at line {node.lineno}")
    assert not offenders, f"raw query construction in the router: {offenders}"


def test_the_router_defines_no_private_helpers():
    """A module-level private in a router is a service that has not moved yet."""
    offenders = [
        node.name
        for node in _tree().body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("_")
    ]
    assert not offenders, f"private helpers still in the router: {offenders}"


def test_the_router_has_no_function_local_imports():
    """A deferred import usually hides a cycle; the cycle is the thing to fix."""
    offenders = []
    for parent in ast.walk(_tree()):
        if not isinstance(parent, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for node in ast.walk(parent):
            if isinstance(node, ast.Import | ast.ImportFrom):
                offenders.append(f"{parent.name} (line {node.lineno})")
    assert not offenders, f"function-local imports: {offenders}"


def test_every_route_is_still_registered():
    """Guard against the split having quietly dropped an endpoint.

    Counted from the decorators rather than hardcoded per path, so adding a route
    does not fail this — only losing one below the count the split started with.
    """
    routes = [
        node
        for node in _tree().body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and any(
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and dec.func.attr in {"get", "post", "patch", "put", "delete"}
            for dec in node.decorator_list
        )
    ]
    assert len(routes) >= 14, f"only {len(routes)} routes survive the split"
