"""Environment, credentials, and deployment settings."""

from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

from pycil.platform.product_config import SystemConfig, get_system_config


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    domain: str = "localhost"
    db_url: str = "postgresql+asyncpg://pycil:changeme@postgres:5432/pycil"
    redis_url: str = "redis://redis:6379/0"
    clerk_secret_key: str = ""
    clerk_jwt_key: str = ""
    clerk_api_url: str = ""
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    clerk_audience: str = ""
    internal_secret: str = "changeme-base64-32-bytes"
    allowed_origins: str = "http://localhost,https://localhost"
    max_body_bytes: int = 1_048_576
    lexi_reference_dataset_fingerprint: str = ""
    assistant_api_key: str = ""
    assistant_base_url: str = ""
    assistant_checkpoint_db_url: str = ""
    assistant_run_deadline_seconds: int = 120
    assistant_max_message_chars: int = 8000
    assistant_context_window_tokens: int = 8_192
    assistant_retention_days: int = 30

    @property
    def system(self) -> SystemConfig:
        return get_system_config()

    @property
    def assistant_psycopg_url(self) -> str:
        configured = self.assistant_checkpoint_db_url or self.db_url
        return configured.replace("postgresql+asyncpg://", "postgresql://", 1)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"production", "prod"}


def validate_production_settings(config: Settings) -> None:
    if not config.is_production:
        return
    required = {
        "DB_URL": config.db_url,
        "REDIS_URL": config.redis_url,
        "INTERNAL_SECRET": config.internal_secret,
        "LEXI_REFERENCE_DATASET_FINGERPRINT": config.lexi_reference_dataset_fingerprint,
    }
    placeholders = ("changeme", "replace-with", "redis-dev-only")
    unsafe = [
        name
        for name, value in required.items()
        if not value
        or any(marker in value.lower() for marker in placeholders)
        or (name == "INTERNAL_SECRET" and len(value) < 32)
    ]
    if not _is_authenticated_redis_url(config.redis_url):
        unsafe.append("REDIS_URL")
    if not config.cors_origins or any(
        origin == "*" or not _is_https_url(origin, origin=True) or "localhost" in origin.lower()
        for origin in config.cors_origins
    ):
        unsafe.append("ALLOWED_ORIGINS")
    if not config.domain or config.domain.lower() == "localhost":
        unsafe.append("DOMAIN")
    if unsafe:
        raise RuntimeError(f"unsafe production configuration: {', '.join(sorted(unsafe))}")


def _is_https_url(value: str, *, origin: bool = False) -> bool:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return False
        return not origin or (parsed.path in {"", "/"} and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


def _is_authenticated_redis_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme.lower() in {"redis", "rediss"}
            and bool(parsed.hostname)
            and bool(parsed.password)
        )
    except ValueError:
        return False


def get_settings() -> Settings:
    return Settings()


settings = get_settings()
