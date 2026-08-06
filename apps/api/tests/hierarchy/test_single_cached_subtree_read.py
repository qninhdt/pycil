"""The cached subtree read has exactly one implementation.

`_defset` existed as two byte-identical 22-line copies — one private to
`hierarchy/router.py`, one to `hierarchy/viewer_stats.py`. Both implemented the
same generation fence: resolve the sense set, re-read the structural generation,
and only publish to cache when it still matches, so a mutation racing the resolve
cannot install a stale set under a fresh generation number.

Two copies of a race-sensitive read is one edit away from divergence, and the
divergence would be invisible — both paths would still return plausible sense
lists, just one of them occasionally stale. So this pins the shape rather than
the behaviour: one implementation, and the callers delegate to it.
"""

import ast
import pathlib

import pytest

HIERARCHY = pathlib.Path(__file__).resolve().parents[2] / "pycil" / "hierarchy"


def _function_bodies(path: pathlib.Path, name: str) -> list[ast.AsyncFunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    ]


def test_the_cached_subtree_read_lives_in_exactly_one_module():
    """`subtree.cached_sense_ids` is the implementation; nothing else reimplements it."""
    implementations = []
    for source in sorted(HIERARCHY.rglob("*.py")):
        for func in _function_bodies(source, "cached_sense_ids"):
            implementations.append((source.name, func))

    assert len(implementations) == 1, (
        f"expected one cached_sense_ids, found {[m for m, _ in implementations]}"
    )
    assert implementations[0][0] == "subtree.py"


def test_no_caller_reimplements_the_generation_fence():
    """A delegating wrapper is fine; a second copy of the fence is not.

    The fence is recognisable by its shape: it calls `current_generation` more
    than once (read it, resolve, re-read to confirm nothing moved). A wrapper
    calls it zero times.
    """
    offenders = []
    for source in sorted(HIERARCHY.rglob("*.py")):
        if source.name == "subtree.py":
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for func in ast.walk(tree):
            if not isinstance(func, ast.AsyncFunctionDef):
                continue
            calls = sum(
                1
                for node in ast.walk(func)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "current_generation"
            )
            if calls > 1:
                offenders.append(f"{source.name}::{func.name}")

    assert not offenders, f"generation fence re-implemented in: {offenders}"


@pytest.mark.parametrize("module", ["router.py", "application/viewer_stats.py"])
def test_the_former_copy_sites_now_delegate(module):
    """Both ex-owners reach the read through `subtree`, not their own copy.

    `router.py` briefly kept a one-line wrapper; it now calls
    `subtree.cached_sense_ids` at each site directly, which is why this asserts on
    the call rather than on a wrapper's presence.
    """
    source = (HIERARCHY / module).read_text(encoding="utf-8")
    assert "cached_sense_ids" in source, f"{module} no longer reaches the shared read"
