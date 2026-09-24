"""A level may use test support, never a fixture from a level above it.

The four levels exist so a failure names its layer, and the cost of running a check
tells you what it proves. Both break the moment a unit test reaches for the running
stack: the suite stops running without Docker, and a failure that came from an HTTP
round trip gets reported as a pure-rule failure.

This is deliberately a source read rather than an import graph. The imports that
violate the rule are exactly the ones a test author writes by hand while moving a
file, and an AST walk catches those without needing to import anything — which
matters, because importing a system module here would itself be the violation.
"""

import ast
import pathlib

import pytest

API_TESTS = pathlib.Path(__file__).resolve().parents[2]

#: What each level may import from the test tree. A level may always import
#: `tests.support` (shared fixtures and protocol doubles) and `tests.conftest`.
#: The rest is what would drag a slower level into a faster one.
ALLOWED_TEST_IMPORTS = {
    "unit": {"tests.support", "tests.conftest"},
    "integration": {"tests.support", "tests.conftest"},
    "system": {"tests.support", "tests.conftest", "tests.system.conftest"},
}


def _test_imports(path: pathlib.Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names if alias.name.startswith("tests")}
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("tests"):
            found.add(node.module or "")
    return found


@pytest.mark.parametrize("level", sorted(ALLOWED_TEST_IMPORTS))
def test_a_level_does_not_import_from_a_slower_level(level: str):
    allowed = ALLOWED_TEST_IMPORTS[level]
    root = API_TESTS / level
    if not root.is_dir():
        pytest.skip(f"level not present: {level}")

    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        for module in _test_imports(path):
            if any(module == prefix or module.startswith(prefix + ".") for prefix in allowed):
                continue
            offenders.append(f"{path.relative_to(API_TESTS)}: imports {module}")

    assert not offenders, (
        "a test imports a fixture from another level; move the fixture to tests/support "
        f"or the test to that level: {offenders}"
    )


def test_the_support_tree_does_not_import_a_level_fixture():
    """`tests/support` is the shared floor, so it must not depend on a level above it."""
    offenders: list[str] = []
    for path in sorted((API_TESTS / "support").rglob("*.py")):
        for module in _test_imports(path):
            if module.startswith("tests.support") or module == "tests.conftest":
                continue
            offenders.append(f"{path.relative_to(API_TESTS)}: imports {module}")

    assert not offenders, f"test support imports a level fixture: {offenders}"
