"""Pycil may know only Lexi's root facade and its public contracts.

This rule does not enforce itself. Reaching into `lexi_ai.infrastructure` compiles,
runs, and passes every other test — it only surfaces later, as wrong data after a
Lexi schema change. So it gets one check, and this is it.

It is deliberately narrow. Static imports are all it reads: `importlib.import_module`
slips straight through, and that is fine, because the threat is not someone
determined to bypass a test. The threat is drift — a deep import added while
implementing something the facade does not cover yet, in a change that otherwise
looks correct.

Two import-linter contracts used to restate the same rule as hand-kept lists of
forbidden Lexi submodules. Both rotted: each still named two modules Lexi had
deleted while missing thirteen it had added, and both passed anyway. Reading the
source needs no list, so a Lexi bump cannot quietly widen the boundary.
"""

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[5]

# Both deployed packages. Parsing the source rather than importing it is what lets
# one test cover both: they are separate uv projects with separate virtualenvs, so
# neither can import the other, but the files are right here.
PACKAGES = (REPO / "apps" / "api" / "pycil", REPO / "apps" / "worker" / "pycil_worker")


def _illegal_lexi_imports(package: pathlib.Path) -> list[str]:
    hits: list[str] = []
    for path in sorted(package.rglob("*.py")):
        where = path.relative_to(REPO)
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if isinstance(node, ast.Import):
                hits += [
                    f"{where}:{node.lineno}: import {alias.name}"
                    for alias in node.names
                    if alias.name.startswith("lexi_ai")
                ]
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("lexi_ai"):
                allowed = node.module == "lexi_ai.contracts" or (
                    node.module == "lexi_ai" and {a.name for a in node.names} == {"Lexicon"}
                )
                if not allowed:
                    hits.append(f"{where}:{node.lineno}: from {node.module}")
    return hits


def test_no_deployed_package_imports_lexi_internals():
    for package in PACKAGES:
        assert package.is_dir(), f"deployed package moved or renamed: {package}"

    hits = [hit for package in PACKAGES for hit in _illegal_lexi_imports(package)]

    assert not hits, f"Lexi implementation imports detected: {hits}"
