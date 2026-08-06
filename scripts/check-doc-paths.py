#!/usr/bin/env python3
"""Fail when a doc cites a repo path that does not exist.

Documentation that names a file is making a checkable claim, and this repo had
accumulated dozens of false ones — paths from the Go era, from the pre-rebuild
frontend, and from modules that had simply moved. A reader cannot tell a stale
path from a real one they should go read, so every false claim devalues the true
ones around it.

Only inline-code paths that look like repo files are checked (`` `apps/api/x.py` ``).
Bare prose is not a claim this can verify, and a path that resolves anywhere under
the repo root counts as present — docs legitimately cite a file by its short name.

`project-changelog.md` is exempt: it records what was true at each release, so a
path that has since moved is history rather than drift.

Usage:
    scripts/check-doc-paths.py [--docs DIR] [--verbose]

Exit status: 0 when every cited path resolves, 1 otherwise.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

# Inline-code spans that look like a repo path: contain a slash or a known source
# extension, and no spaces. `:12-15` line suffixes are stripped before resolving.
CITATION = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|ts|tsx|sh|yml|yaml|json|toml|md))(?::[\d-]+)?`")

# Records history, not current state. A path that has since moved or been deleted
# is the point of these documents rather than drift in them.
#
# `project-overview-pdr.md` and `testing-strategy.md` both declare their historical
# scope in their own first lines; `rehabilitation-report.md` is dated and describes
# a finished operation; `project-roadmap.md` names artifacts that were planned and
# then dropped. Checking any of them would force either deleting real history or
# inventing files to satisfy a linter.
EXEMPT_FILES = {
    "project-changelog.md",
    "project-overview-pdr.md",
    "project-roadmap.md",
    "rehabilitation-report.md",
}

# Lines that describe something as removed are history inside a live document.
REMOVAL_MARKERS = ("Removed ", "removed in ", "deleted in ", "no longer exists")

# Paths that legitimately do not exist in the tree.
EXEMPT_PATHS = {
    ".env",  # created by the operator from .env.example
    ".env.local",
    "package-lock.json",  # pnpm repo; named only to say it is NOT used
}


def cited_paths(text: str) -> set[str]:
    """Paths cited as current. Lines that state a removal are skipped.

    A live document may legitimately record that something was deleted — the claim
    is about the past, and rewriting it to satisfy this check would erase the very
    fact it exists to convey.
    """
    found: set[str] = set()
    for line in text.splitlines():
        if any(marker in line for marker in REMOVAL_MARKERS):
            continue
        found.update(m.group(1) for m in CITATION.finditer(line))
    return found


def resolves(candidate: str) -> bool:
    """Whether a cited path exists anywhere sensible under the repo."""
    if candidate in EXEMPT_PATHS:
        return True
    if (REPO / candidate).exists():
        return True
    # Docs often cite a file by a suffix of its path (`content/service.py`), which
    # is a real reference as long as exactly that tail exists somewhere.
    tail = pathlib.PurePosixPath(candidate)
    for match in REPO.rglob(tail.name):
        if any(part in {".venv", "node_modules", "__pycache__", ".git"} for part in match.parts):
            continue
        if match.as_posix().endswith(candidate):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", type=pathlib.Path, default=REPO / "docs")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    sources = sorted(args.docs.glob("*.md"))
    readme = REPO / "README.md"
    if readme.exists():
        sources.append(readme)

    broken: dict[str, list[str]] = {}
    checked = 0
    for source in sources:
        if source.name in EXEMPT_FILES:
            continue
        for candidate in sorted(cited_paths(source.read_text(encoding="utf-8"))):
            checked += 1
            if not resolves(candidate):
                broken.setdefault(source.name, []).append(candidate)

    if args.verbose:
        print(f"checked {checked} path citations across {len(sources)} documents")

    if broken:
        print("\nDocs cite paths that do not exist:\n", file=sys.stderr)
        for name, paths in sorted(broken.items()):
            print(f"  {name}", file=sys.stderr)
            for path in paths:
                print(f"    {path}", file=sys.stderr)
        total = sum(len(p) for p in broken.values())
        print(f"\n{total} broken citation(s).", file=sys.stderr)
        return 1

    print(f"every cited path resolves ({checked} checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
