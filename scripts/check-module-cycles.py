#!/usr/bin/env python3
"""Report import cycles between the top-level modules of a Python package.

Walks every source file with `ast`, records which sibling top-level modules each
one imports, then reports the strongly-connected components of that graph. Any
component with more than one member is a cycle: the modules in it cannot be
understood, tested, or extracted independently of each other.

Written as a committed gate rather than a one-off query so that a claim like
"this cycle is gone" is reproducible. Run it, diff the output against the
recorded baseline, and a shrinking list is evidence while an absence is not.

Usage:
    check-module-cycles.py <package-dir> [<package-dir> ...] [--baseline FILE]

Exit status:
    0  the cycle set matches the baseline (or no baseline was given)
    1  a cycle appeared that the baseline does not record
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path


# Modules whose imports are NOT attributed to their parent, keyed by package.
#
# One entry, and it is a genuine exemption rather than a convenience: `db.models`
# imports all seven domains' ORM classes for the sole purpose of building
# `target_metadata`, while every domain imports `db.session`/`db.redis`. That
# reads as `db <-> every domain` when edges are aggregated per top-level module.
#
# It is not a real cycle. Only Alembic (`alembic/env.py`) and the test harness
# (`tests/conftest.py`) import `db.models`; no domain does, and no request path
# touches it. `db.session`, `db.redis` and `db.base` — what the domains actually
# import — carry zero domain imports between them, so the runtime graph is
# acyclic. Aggregating a build-time aggregator with the runtime leaves is what
# manufactures the edge.
#
# The exemption is narrow on purpose: it names one file, so a domain import added
# anywhere else under `db/` still shows up as a cycle.
EXEMPT_MODULES: dict[str, frozenset[str]] = {
    "pycil": frozenset({"db.models"}),
}


def top_level_module(package: str, dotted: str) -> str | None:
    """Return the sibling top-level module `dotted` refers to, if any.

    `pycil.learning.service` inside package `pycil` yields `learning`. Anything
    outside the package, and the package root itself, yields None.
    """
    parts = dotted.split(".")
    if len(parts) < 2 or parts[0] != package:
        return None
    return parts[1]


class UnparseableSource(Exception):
    """A source file could not be parsed, so its edges are unknown."""


def imports_of(path: Path, package: str) -> set[str]:
    """Every sibling top-level module imported by one source file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        # Skipping the file would silently drop its edges and could report a
        # cycle as drained when it is merely unread. The interpreter running this
        # script must be new enough for the syntax the project actually uses.
        raise UnparseableSource(
            f"{path}: {exc}\n"
            f"    Running Python {sys.version_info.major}.{sys.version_info.minor}; "
            f"this file needs a newer one.\n"
            f"    Try: cd apps/api && uv run python ../../scripts/check-module-cycles.py ..."
        ) from exc

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if mod := top_level_module(package, alias.name):
                    found.add(mod)
        elif isinstance(node, ast.ImportFrom):
            # `from . import x` and `from .sibling import y` are relative to the
            # file's own module, which is already the module we are attributing
            # the edge to — so only absolute imports can cross a boundary here.
            if node.level == 0 and node.module:
                if mod := top_level_module(package, node.module):
                    found.add(mod)
    return found


def build_graph(package_dir: Path, exempt: frozenset[str] = frozenset()) -> dict[str, set[str]]:
    """Map each top-level module of the package to the siblings it imports.

    `exempt` names dotted module paths (relative to the package, e.g. ``db.models``)
    whose imports are not attributed to their parent module. See EXEMPT_MODULES.
    """
    package = package_dir.name
    graph: dict[str, set[str]] = defaultdict(set)

    for child in sorted(package_dir.iterdir()):
        if child.name.startswith((".", "_")):
            continue
        if child.is_dir():
            module, sources = child.name, sorted(child.rglob("*.py"))
        elif child.suffix == ".py":
            module, sources = child.stem, [child]
        else:
            continue

        graph.setdefault(module, set())
        for source in sources:
            rel = source.relative_to(package_dir).with_suffix("")
            if ".".join(rel.parts) in exempt:
                continue
            for imported in imports_of(source, package):
                if imported != module:  # a module importing itself is not a cycle
                    graph[module].add(imported)

    return graph


def strongly_connected(graph: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan's SCC. Any component of size > 1 is an import cycle.

    Iterative rather than recursive: the whole point of this script is to survive
    pathological graphs, and a deep one would blow the interpreter's stack.
    """
    index_of: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[list[str]] = []
    counter = 0

    for root in sorted(graph):
        if root in index_of:
            continue

        work: list[tuple[str, list[str]]] = [(root, sorted(graph.get(root, ())))]
        index_of[root] = lowlink[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)

        while work:
            node, pending = work[-1]
            if pending:
                child = pending.pop(0)
                if child not in index_of:
                    index_of[child] = lowlink[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, sorted(graph.get(child, ()))))
                elif child in on_stack:
                    lowlink[node] = min(lowlink[node], index_of[child])
                continue

            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])

            if lowlink[node] == index_of[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1:
                    components.append(sorted(component))

    return sorted(components)


def two_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Mutual import pairs, reported separately because they are the easiest to fix."""
    pairs = {
        tuple(sorted((a, b)))
        for a, targets in graph.items()
        for b in targets
        if a in graph.get(b, set())
    }
    return sorted([list(pair) for pair in pairs])


def analyse(package_dir: Path) -> dict:
    exempt = EXEMPT_MODULES.get(package_dir.name, frozenset())
    graph = build_graph(package_dir, exempt)
    return {
        "package": package_dir.name,
        "path": str(package_dir),
        "modules": sorted(graph),
        "exempt_modules": sorted(exempt),
        "mutual_pairs": two_cycles(graph),
        "cycles": strongly_connected(graph),
        "edges": {module: sorted(targets) for module, targets in sorted(graph.items())},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="+", type=Path)
    parser.add_argument(
        "--baseline",
        type=Path,
        help="JSON file of recorded cycles; exit 1 if a cycle appears that it does not list",
    )
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()

    reports = []
    for package_dir in args.packages:
        if not package_dir.is_dir():
            print(f"error: not a directory: {package_dir}", file=sys.stderr)
            return 2
        try:
            reports.append(analyse(package_dir))
        except UnparseableSource as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    for report in reports:
        print(f"\n=== {report['package']} ({len(report['modules'])} modules) ===")
        if report["cycles"]:
            print(f"cycles ({len(report['cycles'])}):")
            for cycle in report["cycles"]:
                print(f"  {' <-> '.join(cycle)}")
        else:
            print("cycles: none")
        if report["mutual_pairs"]:
            print(f"mutual import pairs ({len(report['mutual_pairs'])}):")
            for a, b in report["mutual_pairs"]:
                print(f"  {a} <-> {b}")

    payload = {report["package"]: report for report in reports}

    if args.write_baseline:
        if not args.baseline:
            print("error: --write-baseline needs --baseline", file=sys.stderr)
            return 2
        args.baseline.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"\nbaseline written to {args.baseline}")
        return 0

    if args.baseline:
        if not args.baseline.exists():
            print(f"error: baseline not found: {args.baseline}", file=sys.stderr)
            return 2
        recorded = json.loads(args.baseline.read_text(encoding="utf-8"))
        regressed = False
        for name, report in payload.items():
            base = recorded.get(name, {})
            known = [set(c) for c in base.get("cycles", [])]

            # Subset comparison, not exact-tuple equality. A cycle is a REGRESSION
            # only if its members are not all inside some recorded cycle. Matching
            # whole components exactly gets both directions wrong: breaking one
            # module out of the 7-module component yields a 6-module component that
            # is not in the baseline, so real progress would read as a new cycle.
            for cycle in report["cycles"]:
                members = set(cycle)
                if any(members <= recorded_cycle for recorded_cycle in known):
                    continue
                print(f"\nNEW CYCLE in {name}: {' <-> '.join(cycle)}", file=sys.stderr)
                regressed = True

            # Mutual pairs are compared too. A brand-new mutual import between two
            # modules already inside one component leaves the component list
            # identical, so cycles alone cannot see coupling getting worse.
            known_pairs = {tuple(p) for p in base.get("mutual_pairs", [])}
            for pair in report["mutual_pairs"]:
                if tuple(pair) not in known_pairs:
                    print(f"\nNEW MUTUAL IMPORT in {name}: {pair[0]} <-> {pair[1]}", file=sys.stderr)
                    regressed = True

            for pair in sorted(known_pairs - {tuple(p) for p in report["mutual_pairs"]}):
                print(f"drained pair in {name}: {pair[0]} <-> {pair[1]}")

            recorded_members = set().union(*known) if known else set()
            current_members = set().union(*(set(c) for c in report["cycles"])) or set()
            for module in sorted(recorded_members - current_members):
                print(f"freed in {name}: {module} is no longer in any cycle")

        if regressed:
            return 1
        print("\nno cycle outside the baseline")

    return 0


if __name__ == "__main__":
    sys.exit(main())
