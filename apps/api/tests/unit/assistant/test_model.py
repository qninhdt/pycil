from types import SimpleNamespace

from pydantic import SecretStr

from pycil.app.config import load_config
from pycil.assistant.graph import model


async def test_assistant_disables_native_sdk_retries_and_closes_its_client():
    config = load_config()
    deployment = SimpleNamespace(
        llm_api_key=SecretStr("test"), llm_base_url="https://provider.test"
    )
    async with model(deployment, config.models[0], "medium", 3) as selected:
        sdk = selected.client
        assert sdk.sdk_configuration.retry_config is None
        assert sdk.sdk_configuration.timeout_ms == 3000
        http = sdk.sdk_configuration.async_client
        assert not http.is_closed
    assert http.is_closed
