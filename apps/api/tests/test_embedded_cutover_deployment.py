"""Static deployment contracts for the fresh-schema embedded Lexi cutover."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_compose_migrates_lexi_before_pycil_and_mounts_the_reference_artifact():
    compose = (ROOT / "docker-compose.yml").read_text()

    assert "import lexi_ai.migrations" in compose
    assert "LEXI_DOMAIN_MIGRATION_HEAD" in compose
    assert "LEXI_ALEMBIC=" in compose
    assert "LEXI_REFERENCE_DATASET_PATH:?LEXI_REFERENCE_DATASET_PATH is required" in compose
    assert "lexi-service" not in compose
    assert "pycil-backend" not in compose


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
