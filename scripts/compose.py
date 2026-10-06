"""Compose from canonical DB_URL/REDIS_URL; never print resolved secrets.

Use: python scripts/compose.py --env-file .env up --build
Only loopback URLs are translated to Docker DNS. Remote addresses stay intact.
Official store-image bootstrap variables are derived, not user configuration.
"""

import argparse
import os
import shlex
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def read_environment(path):
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.removeprefix("export ").partition("=")
        key = key.strip()
        if not separator or not key.isidentifier() or key in values:
            raise ValueError("Invalid or duplicate environment key")
        parts = shlex.split(value, comments=True)
        if len(parts) > 1:
            raise ValueError("Quote environment values containing spaces")
        values[key] = parts[0] if parts else ""
    return values


def store_environment(environment):
    db = urlsplit(environment.get("DB_URL", ""))
    redis = urlsplit(environment.get("REDIS_URL", ""))
    if (
        db.scheme != "postgresql+asyncpg"
        or not db.hostname
        or not db.username
        or not db.password
        or not db.path.strip("/")
    ):
        raise ValueError("DB_URL requires a database, username and password")
    if redis.scheme not in {"redis", "rediss"} or not redis.hostname or not redis.password:
        raise ValueError("REDIS_URL requires an address and password")

    def internal(url, host, port):
        if url.hostname not in LOOPBACK:
            return urlunsplit(url)
        credentials = url.netloc.rsplit("@", 1)[0]
        return urlunsplit(url._replace(netloc=f"{credentials}@{host}:{port}"))

    return {
        "_DB_URL": internal(db, "postgres", 5432),
        "_DB_USER": unquote(db.username),
        "_DB_PASSWORD": unquote(db.password),
        "_DB_NAME": unquote(db.path.lstrip("/")),
        "_DB_BIND": f"127.0.0.1:{db.port or 5432}",
        "_REDIS_URL": internal(redis, "redis", 6379),
        "_REDIS_PASSWORD": unquote(redis.password),
        "_REDIS_USER": unquote(redis.username or "default"),
        "_REDIS_BIND": f"127.0.0.1:{redis.port or 6379}",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args, command = parser.parse_known_args()
    # Resolved config prints credentials. Offer the safe validation form only.
    if "config" in command:
        config_options = command[command.index("config") + 1 :]
        if config_options not in (["-q"], ["--quiet"]):
            parser.error("Use only config -q; other config outputs can contain credentials")
    try:
        env = {**read_environment(args.env_file), **os.environ}
        env.update(store_environment(env))
    except Exception:
        parser.exit(2, "Invalid environment file or store URLs; no credentials printed.\n")
    result = subprocess.run(
        ["docker", "compose", "--env-file", "/dev/null", *command],
        cwd=ROOT,
        env=env,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
