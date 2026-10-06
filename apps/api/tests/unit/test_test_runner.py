import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("test_runner", ROOT / "scripts/test_api.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def fake_commands(monkeypatch, *, failure=None, pytest_status=0, cleanup_failure=False):
    calls = []

    def command(args, **kwargs):
        calls.append((args, kwargs))
        phase = (
            "pytest"
            if args[0] == "uv"
            else next(
                (name for name in ("up", "down", "port", "info", "version") if name in args), None
            )
        )
        if phase == "down" and cleanup_failure:
            raise subprocess.CalledProcessError(1, args)
        if phase == failure:
            raise subprocess.CalledProcessError(1, args)
        if failure == "interrupt" and phase == "pytest":
            raise KeyboardInterrupt
        output = ""
        if phase == "port":
            output = "127.0.0.1:54321\n" if "postgres" in args else "127.0.0.1:54322\n"
        return subprocess.CompletedProcess(args, pytest_status if phase == "pytest" else 0, output)

    monkeypatch.setattr(runner, "command", command)
    return calls


def test_managed_runner_ignores_application_and_inherited_test_targets(monkeypatch):
    for name in (
        "DB_URL",
        "REDIS_URL",
        "TEST_DB_URL",
        "TEST_REDIS_URL",
        "UV_ENV_FILE",
        "COMPOSE_FILE",
        "COMPOSE_PROJECT_NAME",
        "COMPOSE_PROFILES",
        "CONFIG_PATH",
        "PYTEST_ADDOPTS",
    ):
        monkeypatch.setenv(name, "must-not-be-used")
    calls = fake_commands(monkeypatch)
    assert runner.run_tests(["tests/integration/test_library.py", "-q"]) == 0
    up = next(args for args, _ in calls if "up" in args)
    down = next(args for args, _ in calls if "down" in args)
    project = up[up.index("--project-name") + 1]
    assert project.startswith("pycil-test-")
    assert down[down.index("--project-name") + 1] == project
    assert up[up.index("--file") + 1] == str(ROOT / "docker-compose.test.yml")
    assert "--wait" in up and "--volumes" in down
    pytest_command, options = next(call for call in calls if call[0][0] == "uv")
    assert pytest_command == [
        "uv",
        "run",
        "--locked",
        "--no-env-file",
        "pytest",
        "tests/integration/test_library.py",
        "-q",
    ]
    assert options["cwd"] == ROOT / "apps/api"
    env = options["env"]
    assert env["TEST_DB_URL"] == ("postgresql+asyncpg://test:test@127.0.0.1:54321/rewrite_test")
    assert env["TEST_REDIS_URL"] == "redis://127.0.0.1:54322/15"
    assert env["CONFIG_PATH"] == str(ROOT / "config/config.yaml")
    assert not any(key.startswith("COMPOSE_") for key in env)
    assert not {"DB_URL", "REDIS_URL", "UV_ENV_FILE", "PYTEST_ADDOPTS"} & env.keys()
    assert all("must-not-be-used" not in options["env"].values() for _, options in calls)


@pytest.mark.parametrize("phase", ["up", "port", "pytest", "interrupt"])
def test_failure_or_interrupt_always_cleans_own_project(monkeypatch, phase):
    calls = fake_commands(monkeypatch, failure=phase)
    assert runner.run_tests(["tests", "-q"]) == (130 if phase == "interrupt" else 1)
    assert "down" in calls[-1][0]
    assert "--volumes" in calls[-1][0]
    if phase in {"up", "port"}:
        assert not any(args[0] == "uv" for args, _ in calls)


@pytest.mark.parametrize("code", [0, 1, 5, -15])
def test_pytest_exit_status_preserved(monkeypatch, code):
    calls = fake_commands(monkeypatch, pytest_status=code)
    assert runner.run_tests(["tests", "-q"]) == (128 - code if code < 0 else code)
    assert "down" in calls[-1][0]


@pytest.mark.parametrize("phase", ["info", "version"])
def test_missing_docker_does_not_start_stores(monkeypatch, phase):
    calls = fake_commands(monkeypatch, failure=phase)
    assert runner.run_tests(["tests", "-q"]) == 1
    assert not any("up" in args or "down" in args for args, _ in calls)


def test_cleanup_failure_is_not_reported_as_success(monkeypatch):
    fake_commands(monkeypatch, cleanup_failure=True)
    assert runner.run_tests(["tests", "-q"]) == 1


def test_concurrent_runs_have_distinct_projects(monkeypatch):
    calls = fake_commands(monkeypatch)
    assert runner.run_tests(["tests", "-q"]) == 0
    assert runner.run_tests(["tests", "-q"]) == 0
    projects = [args[args.index("--project-name") + 1] for args, _ in calls if "up" in args]
    assert len(set(projects)) == 2


@pytest.mark.parametrize(
    "binding",
    [
        "0.0.0.0:5432",
        "[::1]:5432",
        "127.0.0.1:0",
        "127.0.0.1:65536",
        "127.0.0.1:abc",
        "127.0.0.1:5432\n127.0.0.1:5433",
    ],
)
def test_port_rejects_non_loopback_or_invalid_bindings(monkeypatch, binding):
    monkeypatch.setattr(
        runner, "command", lambda *args, **kwargs: subprocess.CompletedProcess([], 0, binding)
    )
    with pytest.raises(ValueError):
        runner.port(["docker", "compose"], "postgres", 5432, {})


def test_manifest_has_only_isolated_stores_and_matches_ci_images():
    manifest = yaml.safe_load((ROOT / "docker-compose.test.yml").read_text())
    services = manifest["services"]
    ci = yaml.safe_load((ROOT / ".github/workflows/test.yml").read_text())
    assert set(services) == {"postgres", "redis"}
    assert "volumes" not in manifest
    for name, service in services.items():
        assert service["image"] == ci["jobs"]["backend"]["services"][name]["image"]
        assert service["ports"] == [f"127.0.0.1::{5432 if name == 'postgres' else 6379}"]
        assert "healthcheck" in service and "tmpfs" in service
        assert "volumes" not in service


def test_command_captures_output_and_propagates_failure():
    result = runner.command([sys.executable, "-c", "print('ready')"], env=os.environ, capture=True)
    assert result.stdout == "ready\n"
    with pytest.raises(subprocess.CalledProcessError) as caught:
        runner.command([sys.executable, "-c", "raise SystemExit(5)"], env=os.environ)
    assert caught.value.returncode == 5


def test_command_timeout_terminates_child():
    with pytest.raises(subprocess.TimeoutExpired):
        runner.command(
            [sys.executable, "-c", "import time; time.sleep(60)"], env=os.environ, timeout=0.1
        )
