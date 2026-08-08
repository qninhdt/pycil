"""Compatibility entry point for the repository-level error-code generator.

The generator belongs at the repository root because it reads both the API and
the web client. Keep this historical ``apps/api/scripts`` command working, but
avoid maintaining a second extractor with a different view of the wire contract.
"""

from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "scripts" / "extract-error-codes.py"),
        run_name="__main__",
    )
