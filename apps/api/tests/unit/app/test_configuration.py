import pytest
from pydantic import ValidationError

from pycil.app.config import AppConfig, load_config
from pycil.app.settings import ApiSettings, ProcessSettings, WorkerSettings


def test_duplicate_yaml_keys_and_invalid_policy_are_safe_failures(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("system:\n  http:\n    max_body_bytes: 1\n  http:\n    max_body_bytes: 2\n")
    with pytest.raises(ValueError, match="Duplicate config key"):
        load_config(path)
    data = load_config().model_dump(mode="json")
    data["assistant"]["defaults"]["model"] = "missing"
    with pytest.raises(ValidationError, match="default assistant model"):
        AppConfig.model_validate(data)
    data = load_config().model_dump(mode="json")
    data["library"]["page_size"] = data["library"]["max_page_size"] + 1
    with pytest.raises(ValidationError):
        AppConfig.model_validate(data)
    data = load_config().model_dump(mode="json")
    data["assistant"]["models"].append(data["assistant"]["models"][0])
    with pytest.raises(ValidationError, match="duplicate model ID"):
        AppConfig.model_validate(data)


@pytest.mark.parametrize(
    "path,value",
    [
        ("study.grading.decision_threshold", -0.1),
        ("study.grading.decision_threshold", 1.1),
        ("study.grading.decision_threshold", float("nan")),
        ("system.database.application_pool.connect_timeout_seconds", 0),
        ("system.database.checkpoint_pool.timeout_seconds", -1),
        ("system.database.checkpoint_pool.startup_timeout_seconds", float("inf")),
        ("system.telemetry.traces.max_queue_size", 0),
        ("system.telemetry.traces.max_export_batch_size", 2049),
        ("system.telemetry.traces.schedule_delay_seconds", 0),
        ("system.telemetry.traces.export_timeout_seconds", float("inf")),
        ("system.telemetry.metrics.export_interval_seconds", 0),
        ("system.telemetry.metrics.export_timeout_seconds", -1),
        ("system.telemetry.metrics.shutdown_timeout_seconds", 0),
    ],
)
def test_grading_database_and_telemetry_reject_invalid_budgets(path, value):
    data = load_config().model_dump(mode="json")
    owner = data
    *parts, name = path.split(".")
    for part in parts:
        owner = owner[part]
    owner[name] = value
    with pytest.raises(ValidationError):
        AppConfig.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("db_url", "sqlite:///content.sqlite"),
        ("redis_url", "http://redis.test"),
        ("llm_base_url", "https://user:secret@provider.test"),
        ("allowed_origins", ["https://web.test/path"]),
        ("allowed_origins", ["*"]),
    ],
)
def test_deployment_rejects_nonserver_addresses_and_credentials_in_service_urls(field, value):
    values = dict(
        db_url="postgresql+asyncpg://test:test@db.test/app",
        redis_url="redis://redis.test/0",
        clerk_jwks_url="https://identity.test/jwks",
        clerk_issuer="https://identity.test",
        clerk_audience=None,
        clerk_secret_key="test-only",
        allowed_origins=["https://web.test"],
        llm_api_key="test-only",
        llm_base_url="https://provider.test/v1",
        decision_api_key="test-only",
        decision_base_url="https://decision.test",
    )
    with pytest.raises(ValidationError):
        ApiSettings(**(values | {field: value}))


@pytest.mark.parametrize("missing", [None, "LLM_API_KEY", "LLM_BASE_URL"])
def test_deployment_loads_llm_environment_and_requires_both_values(monkeypatch, missing):
    variables = {
        "DB_URL": "postgresql+asyncpg://test:test@db.test/app",
        "REDIS_URL": "redis://redis.test/0",
        "CLERK_JWKS_URL": "https://identity.test/jwks",
        "CLERK_ISSUER": "https://identity.test",
        "CLERK_SECRET_KEY": "identity-test-only",
        "LLM_API_KEY": "llm-test-only",
        "LLM_BASE_URL": "https://provider.test/v1",
        "DECISION_API_KEY": "decision-test-only",
        "DECISION_BASE_URL": "https://decision.test",
        "CLERK_AUDIENCE": "",
        "ALLOWED_ORIGINS": "",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector.test:4318",
        "SERVICE_VERSION": "release-immutable",
        "DEPLOYMENT_ENVIRONMENT": "local",
        "GIT_SHA": "a" * 40,
        "OTEL_SERVICE_NAME": "pycil-api",
        "OTEL_TRACES_SAMPLER_ARG": "1",
    }
    for key, value in variables.items():
        monkeypatch.setenv(key, value)
    if missing is not None:
        monkeypatch.delenv(missing)
        with pytest.raises(ValueError, match=f"Missing deployment variables: {missing}"):
            ApiSettings.from_environment()
    else:
        deployment = ApiSettings.from_environment()
        assert deployment.llm_api_key.get_secret_value() == "llm-test-only"
        assert deployment.llm_base_url == "https://provider.test/v1"
        assert "llm-test-only" not in repr(deployment)
        assert deployment.otel_endpoint == "http://collector.test:4318"
        assert deployment.service_version == "release-immutable"
        assert deployment.deployment_environment == "local"
        assert deployment.otel_sample_ratio == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"otel_endpoint": "file:///tmp/export"},
        {"otel_endpoint": "http://user:secret@collector.test"},
        {"otel_endpoint": "http://collector.test?token=private"},
        {"service_version": None},
        {"deployment_environment": None},
        {"otel_sample_ratio": 1.1},
        {"otel_sample_ratio": float("nan")},
    ],
)
def test_telemetry_configuration_requires_safe_destination_and_identity(overrides):
    values = dict(
        db_url="postgresql+asyncpg://test:test@db.test/app",
        redis_url="redis://redis.test/0",
        clerk_jwks_url="https://identity.test/jwks",
        clerk_issuer="https://identity.test",
        clerk_audience=None,
        clerk_secret_key="test-only",
        allowed_origins=[],
        llm_api_key="test-only",
        llm_base_url="https://provider.test/v1",
        decision_api_key="test-only",
        decision_base_url="https://decision.test",
        otel_endpoint="http://collector.test:4318",
        service_version="release-immutable",
        deployment_environment="local",
    )
    with pytest.raises(ValidationError):
        ApiSettings(**(values | overrides))


def test_api_and_worker_settings_are_siblings_and_cors_parsing_is_api_owned(monkeypatch):
    variables = {
        "DB_URL": "postgresql+asyncpg://test:test@db.test/app",
        "REDIS_URL": "redis://redis.test/0",
        "LLM_API_KEY": "test-only",
        "LLM_BASE_URL": "https://provider.test/v1",
    }
    for name in ProcessSettings.model_fields:
        monkeypatch.delenv(ProcessSettings.environment_names.get(name, name.upper()), raising=False)
    for name, value in variables.items():
        monkeypatch.setenv(name, value)
    worker = WorkerSettings.from_environment()
    assert worker.otel_service_name == "pycil-worker"
    assert issubclass(ApiSettings, ProcessSettings) and issubclass(WorkerSettings, ProcessSettings)
    assert not issubclass(ApiSettings, WorkerSettings)
    assert (
        not {"allowed_origins", "clerk_secret_key", "decision_api_key"}
        & WorkerSettings.model_fields.keys()
    )
    api = ApiSettings(
        **worker.model_dump(exclude={"otel_service_name"}),
        clerk_jwks_url="https://identity.test/jwks",
        clerk_issuer="https://identity.test",
        clerk_secret_key="test-only",
        decision_api_key="test-only",
        decision_base_url="https://decision.test",
        allowed_origins=" https://web.test, ,http://localhost:3000 ",
    )
    assert api.allowed_origins == ["https://web.test", "http://localhost:3000"]
    assert api.otel_service_name == "pycil-api"
