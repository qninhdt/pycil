"""Runtime configuration (pydantic-settings).

Env-driven with dev defaults. Pycil owns its Postgres database; dictionary
content is reached only through the separately deployed Lexi service.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- pycil core ----------------------------------------------------------
    environment: str = "development"
    domain: str = "localhost"
    db_url: str = "postgresql+asyncpg://pycil:changeme@postgres:5432/pycil"
    redis_url: str = "redis://redis:6379/0"

    # --- auth ----------------------------------------------------------------
    jwt_secret: str = "changeme-base64-32-bytes"
    jwt_secret_previous: str = ""
    jwt_max_age_seconds: int = 604800
    google_client_id: str = ""
    google_client_secret: str = ""
    oauth_redirect_uris: str = ""
    dev_identity_enabled: bool = False
    dev_identity_email: str = "dev@pycil.local"
    internal_secret: str = "changeme-base64-32-bytes"

    # --- CORS / origins ------------------------------------------------------
    allowed_origins: str = "http://localhost,https://localhost"
    max_body_bytes: int = 1_048_576

    # --- Centrifugo ----------------------------------------------------------
    centrifugo_url: str = "http://centrifugo:8000"
    centrifugo_api_key: str = "changeme-centrifugo-api-key"
    centrifugo_token_hmac_secret: str = "changeme-centrifugo-token-secret"

    # --- Lexi service (internal network only) --------------------------------
    lexi_service_url: str = "http://lexi-service:8443"
    lexi_service_token: str = ""
    lexi_reference_dataset_fingerprint: str = ""
    lexi_service_timeout_seconds: float = 15
    lexi_generation_timeout_seconds: float = 120

    # --- assistant (isolated OpenAI-compatible provider + durable state) ----
    assistant_api_key: str = ""
    assistant_model: str = "gpt-4o-mini"
    assistant_base_url: str = ""
    assistant_checkpoint_db_url: str = ""
    assistant_timeout_seconds: int = 45
    assistant_run_deadline_seconds: int = 120
    assistant_max_output_tokens: int = 800
    assistant_max_tool_calls: int = 12
    assistant_max_message_chars: int = 8000
    assistant_per_user_concurrency: int = 2
    assistant_global_concurrency: int = 50
    assistant_action_ttl_seconds: int = 900
    assistant_retention_days: int = 30
    assistant_audit_retention_days: int = 90
    assistant_monthly_budget_usd: float = 0.0
    assistant_estimated_cost_per_1k_tokens_usd: float = 0.01
    assistant_requests_per_minute: int = 30

    @property
    def assistant_psycopg_url(self) -> str:
        """Dedicated psycopg URL; never pass SQLAlchemy's asyncpg DSN to LangGraph."""
        configured = self.assistant_checkpoint_db_url or self.db_url
        return configured.replace("postgresql+asyncpg://", "postgresql://", 1)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def allowed_oauth_redirect_uris(self) -> set[str]:
        return {uri.strip() for uri in self.oauth_redirect_uris.split(",") if uri.strip()}


def validate_production_settings(config: Settings) -> None:
    """Fail closed for deploy-time placeholders without impairing local tests.

    Development intentionally has convenient defaults; production must provide
    real secrets, exact browser origins, and an explicit OAuth callback allowlist.
    """
    if config.environment.lower() not in {"production", "prod"}:
        return

    required = {
        "JWT_SECRET": config.jwt_secret,
        "INTERNAL_SECRET": config.internal_secret,
        "CENTRIFUGO_API_KEY": config.centrifugo_api_key,
        "CENTRIFUGO_TOKEN_HMAC_SECRET": config.centrifugo_token_hmac_secret,
        "LEXI_SERVICE_TOKEN": config.lexi_service_token,
        "LEXI_REFERENCE_DATASET_FINGERPRINT": config.lexi_reference_dataset_fingerprint,
        "GOOGLE_CLIENT_ID": config.google_client_id,
        "GOOGLE_CLIENT_SECRET": config.google_client_secret,
    }
    unsafe = [name for name, value in required.items() if not value or "changeme" in value.lower()]
    origins = config.cors_origins
    if not origins or any(origin == "*" or "localhost" in origin for origin in origins):
        unsafe.append("ALLOWED_ORIGINS")
    if not config.allowed_oauth_redirect_uris:
        unsafe.append("OAUTH_REDIRECT_URIS")
    if not config.domain or config.domain == "localhost":
        unsafe.append("DOMAIN")
    if unsafe:
        raise RuntimeError(f"unsafe production configuration: {', '.join(sorted(unsafe))}")


def get_settings() -> Settings:
    return Settings()


settings = get_settings()
