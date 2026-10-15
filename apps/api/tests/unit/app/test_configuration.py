import pytest
from pydantic import ValidationError

from pycil.app.config import AppConfig, load_config
from pycil.app.settings import Deployment


def test_duplicate_yaml_keys_and_invalid_policy_are_safe_failures(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("runtime:\n  caches: 1\n  caches: 2\n")
    with pytest.raises(ValueError, match="Duplicate product-policy key"):
        load_config(path)
    data = load_config().model_dump(mode="json")
    data["product"]["assistant"]["defaults"]["model"] = "missing"
    with pytest.raises(ValidationError, match="default assistant model"):
        AppConfig.model_validate(data)
    data = load_config().model_dump(mode="json")
    data["product"]["library"]["pagination"]["page_size"] = (
        data["product"]["projections"]["max_page_size"] + 1
    )
    with pytest.raises(ValidationError):
        AppConfig.model_validate(data)
    data = load_config().model_dump(mode="json")
    data["product"]["assistant"]["models"].append(data["product"]["assistant"]["models"][0])
    with pytest.raises(ValidationError, match="duplicate model ID"):
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
        Deployment(**(values | {field: value}))


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
    }
    for key, value in variables.items():
        monkeypatch.setenv(key, value)
    if missing is not None:
        monkeypatch.delenv(missing)
        with pytest.raises(ValueError, match=f"Missing deployment variables: {missing}"):
            Deployment.from_environment()
    else:
        deployment = Deployment.from_environment()
        assert deployment.llm_api_key.get_secret_value() == "llm-test-only"
        assert deployment.llm_base_url == "https://provider.test/v1"
        assert "llm-test-only" not in repr(deployment)
