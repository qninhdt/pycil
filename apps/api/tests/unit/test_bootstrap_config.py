import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

from pycil.config import Deployment, ProductConfig, load_config


def test_import_needs_neither_yaml_secrets_nor_network():
    env = os.environ | {"PYCIL_CONFIG_PATH": "/does-not-exist/policy.yaml"}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import socket
def forbidden(*args, **kwargs):
    raise AssertionError('Import must not connect to services')
socket.socket.connect = forbidden
import pycil.main
import pycil.worker
import pycil.migrate
assert pycil.main.create_app().title == 'Pycil'
""",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["account"]["defaults"].update(timezone="Not/AZone"),
        lambda d: d["account"].update(locales=["en", "en"]),
        lambda d: d["models"][0].update(id=""),
        lambda d: d["models"][0].update(efforts=["none", "none"]),
        lambda d: d["models"][0].update(input_units_per_token="NaN"),
        lambda d: d["generation"]["worker"].update(max_attempts=0),
        lambda d: d["learning"]["fsrs"].update(desired_retention=float("inf")),
    ],
)
def test_invalid_product_policy_fails_closed(config, mutate):
    data = config.model_dump(mode="json")
    mutate(data)
    with pytest.raises((ValidationError, ValueError)):
        ProductConfig.model_validate(data)


def test_config_error_does_not_echo_input(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("plans: unexpected-secret-sentinel\n")
    with pytest.raises(ValueError, match="Invalid product policy") as caught:
        load_config(path)
    assert "unexpected-secret-sentinel" not in str(caught.value)


def test_missing_environment_lists_only_variable_names(monkeypatch):
    monkeypatch.setattr(os, "environ", {"DB_URL": "password-sentinel"})
    with pytest.raises(ValueError, match="Missing deployment variables") as caught:
        Deployment.from_environment()
    assert "password-sentinel" not in str(caught.value)


def test_worker_missing_configuration_fails_without_exposing_environment():
    result = subprocess.run(
        [sys.executable, "-m", "pycil.worker"],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "DB_URL": "password-sentinel"},
    )
    assert result.returncode == 1
    assert "Worker failed" in result.stderr
    assert "password-sentinel" not in result.stdout + result.stderr


def test_migration_cli_failure_does_not_dump_target_credentials():
    result = subprocess.run(
        [sys.executable, "-m", "pycil.migrate", "--database-url", "password-sentinel"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Migration gate failed" in result.stderr
    assert "password-sentinel" not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr
