"""Runtime configuration (pydantic-settings).

Env-driven with dev defaults. Two databases live on the same node: pycil's own
Postgres (``db_url``) and lexi-ai's separate dictionary DB (``lexi_db_url``). The
``LEXI_*`` values are passed through to lexi-ai's own Settings at client build.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- pycil core ----------------------------------------------------------
    db_url: str = "postgresql+asyncpg://pycil:changeme@postgres:5432/pycil"
    redis_url: str = "redis://redis:6379/0"

    # --- auth ----------------------------------------------------------------
    jwt_secret: str = "changeme-base64-32-bytes"
    jwt_secret_previous: str = ""
    jwt_max_age_seconds: int = 604800
    google_client_id: str = ""
    google_client_secret: str = ""
    internal_secret: str = "changeme-base64-32-bytes"

    # --- CORS / origins ------------------------------------------------------
    allowed_origins: str = "http://localhost,https://localhost"
    max_body_bytes: int = 1_048_576

    # --- Centrifugo ----------------------------------------------------------
    centrifugo_url: str = "http://centrifugo:8000"
    centrifugo_api_key: str = "changeme-centrifugo-api-key"
    centrifugo_token_hmac_secret: str = "changeme-centrifugo-token-secret"

    # --- lexi-ai (separate DB + LLM + Cambridge source) ----------------------
    lexi_db_url: str = "sqlite+aiosqlite:///./lexi.db"
    # Any endpoint implementing OpenAI chat-completions is supported.
    lexi_llm_base_url: str = ""
    lexi_llm_api_key: str = ""
    lexi_llm_model: str = "gpt-4o-mini"
    lexi_cambridge_db_path: str = "/data/cambridge"

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


def get_settings() -> Settings:
    return Settings()


settings = get_settings()
