"""Content dependencies: the shared authenticated Lexi HTTP client."""

from pycil.config import settings
from pycil.content.lexi_http import LexiHttpClient
from pycil.content.lexi_port import LexiClient

_client: LexiHttpClient | None = None


def get_lexi_client() -> LexiClient:
    global _client
    if _client is None:
        _client = LexiHttpClient(
            settings.lexi_service_url,
            settings.lexi_service_token,
            settings.lexi_reference_dataset_fingerprint,
            timeout_seconds=settings.lexi_service_timeout_seconds,
            generation_timeout_seconds=settings.lexi_generation_timeout_seconds,
        )
    return _client


async def close_lexi_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
