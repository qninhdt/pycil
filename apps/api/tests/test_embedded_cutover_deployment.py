"""Static deployment contracts for the fresh-schema embedded Lexi cutover."""

from pathlib import Path

import lexi_ai.migrations

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[3]


def _installed_lexi_migration_head() -> str:
    """Resolve the alembic head of the Lexi build this repository pins."""
    ini = Path(lexi_ai.migrations.__file__).parent / "alembic.ini"
    heads = ScriptDirectory.from_config(Config(str(ini))).get_heads()
    assert len(heads) == 1, f"Lexi must expose exactly one migration head, got {heads}"
    return heads[0]


def test_compose_migrates_lexi_before_pycil_and_mounts_the_reference_artifact():
    compose = (ROOT / "docker-compose.yml").read_text()

    assert "import lexi_ai.migrations" in compose
    assert "LEXI_DOMAIN_MIGRATION_HEAD" in compose
    assert "LEXI_ALEMBIC=" in compose
    assert "LEXI_REFERENCE_DATASET_PATH:?LEXI_REFERENCE_DATASET_PATH is required" in compose
    assert "lexi-service" not in compose
    assert "pycil-backend" not in compose


def test_migration_gate_expects_the_installed_lexi_head():
    """The gate compares `alembic current` against this default.

    A stale default fails the equality check after the migration succeeds, which
    aborts the container before Pycil's own migrations run. Deriving the expected
    value from the installed package keeps the gate honest across Lexi bumps.
    """
    head = _installed_lexi_migration_head()
    compose = (ROOT / "docker-compose.yml").read_text()
    env_example = (ROOT / ".env.example").read_text()

    assert f"LEXI_DOMAIN_MIGRATION_HEAD: ${{LEXI_DOMAIN_MIGRATION_HEAD:-{head}}}" in compose
    assert f"LEXI_DOMAIN_MIGRATION_HEAD={head}" in env_example


def test_lexi_provider_credentials_are_worker_only():
    compose = (ROOT / "docker-compose.yml").read_text()
    api_section = compose.split("  api:", 1)[1].split("  worker:", 1)[0]
    worker_section = compose.split("  worker:", 1)[1]

    assert "*lexi-provider-env" not in api_section
    assert "*lexi-provider-env" in worker_section


def test_rehearsal_uses_empty_compose_volumes_and_api_readiness():
    rehearsal = (ROOT / "scripts" / "rehearse-fresh-schema.sh").read_text()
    deploy = (ROOT / "scripts" / "deploy.sh").read_text()

    assert "down --volumes --remove-orphans" in rehearsal
    assert 'run --rm migrate' in rehearsal
    assert "/health/ready" in rehearsal
    assert "LEXI_REFERENCE_DATASET_SHA256" in deploy
