"""Build the unreleased enum-capable dependency; never publish or alter Lexi's checkout."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

VERSION = "0.1.0+pycil.20261002"
ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="explicit enum-capable Lexi checkout")
    parser.add_argument("--replace", action="store_true", help="replace a changed local artifact")
    args = parser.parse_args()
    source = args.source.resolve()
    files = [source / name for name in ("pyproject.toml", "README.md", "LICENSE")]
    files += sorted(
        path
        for path in (source / "lexi_ai").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )
    if len(files) <= 3 or any(not path.is_file() for path in files):
        parser.error("source must contain Lexi package, project metadata, README and license")
    destination = ROOT / "vendor/lexi-ai"
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pycil-lexi-", dir="/tmp/opencode") as directory:
        stage = Path(directory)
        for path in files:
            target = stage / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        metadata = stage / "pyproject.toml"
        text = metadata.read_text()
        if text.count('version = "0.1.0"') != 1:
            parser.error("unexpected baseline version; review local artifact version explicitly")
        metadata.write_text(text.replace('version = "0.1.0"', f'version = "{VERSION}"'))
        environment = {**os.environ, "SOURCE_DATE_EPOCH": "1790899200"}
        subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(stage / "wheel"), str(stage)],
            check=True,
            env=environment,
        )
        wheel, = (stage / "wheel").glob("*.whl")
        target = destination / wheel.name
        if target.exists() and digest(target) != digest(wheel) and not args.replace:
            parser.error("artifact differs; inspect source changes before using --replace")
        shutil.copyfile(wheel, target)
        provenance = {
            "version": VERSION,
            "published": False,
            "source_head": subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
            ).strip(),
            "source_files_sha256": {str(p.relative_to(source)): digest(p) for p in files},
            "wheel": wheel.name,
            "wheel_sha256": digest(wheel),
            "source_date_epoch": environment["SOURCE_DATE_EPOCH"],
        }
        (destination / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
        (destination / "SHA256SUMS").write_text(f"{digest(wheel)}  {wheel.name}\n")
        print(f"Built {target.relative_to(ROOT)} (unreleased local artifact)")


if __name__ == "__main__":
    main()
