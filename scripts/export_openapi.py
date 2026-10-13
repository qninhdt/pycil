"""Export OpenAPI without initializing stores, providers or application credentials."""

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path)
    args = parser.parse_args()
    result = subprocess.run(
        [
            "uv",
            "run",
            "--locked",
            "python",
            "-c",
            "import json; from pycil.app.factory import create_app; "
            "print(json.dumps(create_app().openapi(), indent=2, ensure_ascii=False))",
        ],
        cwd=ROOT / "apps/api",
        check=True,
        capture_output=True,
    )
    if args.output:
        args.output.write_bytes(result.stdout)
    else:
        print(result.stdout.decode(), end="")


if __name__ == "__main__":
    main()
