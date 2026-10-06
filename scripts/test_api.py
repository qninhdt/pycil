"""Run pytest with automatically managed, isolated PostgreSQL and Redis stores."""

import os
import signal
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
RUNNER_ERRORS = (OSError, ValueError, subprocess.SubprocessError)


def command(args, *, env, cwd=ROOT, capture=False, check=True, timeout=None):
    # A separate group lets cancellation stop uv/pytest or Compose before cleanup.
    with subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        start_new_session=True,
        stdout=subprocess.PIPE if capture else None,
        text=True,
    ) as process:
        try:
            stdout, _ = process.communicate(timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate()
            raise
        if check and process.returncode:
            raise subprocess.CalledProcessError(process.returncode, args)
        return subprocess.CompletedProcess(args, process.returncode, stdout)


def port(compose, service, target, env):
    binding = command([*compose, "port", service, str(target)], env=env, capture=True).stdout
    host, separator, value = binding.strip().partition(":")
    if host != "127.0.0.1" or separator != ":" or not value.isdecimal():
        raise ValueError("Test service did not publish exactly one loopback port")
    number = int(value)
    if not 1 <= number <= 65535:
        raise ValueError("Invalid test service port")
    return number


def run_tests(arguments):
    # Ignore inherited test endpoints too: managed mode only uses stores created here.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("COMPOSE_")
        and key
        not in {
            "DB_URL",
            "REDIS_URL",
            "TEST_DB_URL",
            "TEST_REDIS_URL",
            "UV_ENV_FILE",
            "CONFIG_PATH",
            "PYTEST_ADDOPTS",
        }
    }
    env["CONFIG_PATH"] = str(ROOT / "config/config.yaml")
    project = "pycil-test-" + uuid4().hex
    compose = [
        "docker",
        "compose",
        "--env-file",
        os.devnull,
        "--project-name",
        project,
        "--file",
        str(ROOT / "docker-compose.test.yml"),
    ]
    status = 1
    started = False
    try:
        command(["docker", "compose", "version"], env=env, capture=True, timeout=15)
        command(["docker", "info"], env=env, capture=True, timeout=15)
        print(f"Starting disposable test stores ({project})...", flush=True)
        # Cleanup even when Compose creates just one container before startup fails.
        started = True
        command(
            [*compose, "up", "--detach", "--wait", "--wait-timeout", "90", "--pull", "missing"],
            env=env,
        )
        db_port = port(compose, "postgres", 5432, env)
        redis_port = port(compose, "redis", 6379, env)
        env["TEST_DB_URL"] = f"postgresql+asyncpg://test:test@127.0.0.1:{db_port}/rewrite_test"
        env["TEST_REDIS_URL"] = f"redis://127.0.0.1:{redis_port}/15"
        result = command(
            ["uv", "run", "--locked", "--no-env-file", "pytest", *arguments],
            env=env,
            cwd=ROOT / "apps/api",
            check=False,
        )
        status = result.returncode if result.returncode >= 0 else 128 - result.returncode
    except KeyboardInterrupt:
        print("Test run interrupted; cleaning up its stores.", file=sys.stderr)
        status = 130
    except RUNNER_ERRORS:
        print(
            "Test runner failed. Check local Docker/Compose and uv availability, "
            "image downloads, and service health. No application database was used.",
            file=sys.stderr,
        )
    finally:
        if started:
            # Do not let a second Ctrl-C/SIGTERM strand containers during teardown.
            previous = {
                s: signal.signal(s, signal.SIG_IGN) for s in (signal.SIGINT, signal.SIGTERM)
            }
            try:
                print(f"Removing disposable test stores ({project})...", flush=True)
                command([*compose, "down", "--volumes", "--timeout", "5"], env=env, timeout=30)
            except RUNNER_ERRORS:
                print(
                    f"Cleanup failed for project {project}; retry its exact Compose down "
                    "command with docker-compose.test.yml. Do not prune other resources.",
                    file=sys.stderr,
                )
                status = status or 1
            finally:
                for signum, handler in previous.items():
                    signal.signal(signum, handler)
    return status


def interrupted(signum, frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(run_tests(sys.argv[1:] or ["tests", "-q"]))
