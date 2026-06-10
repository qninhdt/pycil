from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Pycil-core runtime config. Loaded from env or .env file.

    Feature-flag boundary (two intentionally-separate systems):
      - Env flags here (`enforce_tiers`, `llm_judge_enabled`,
        `question_bank_prewarm_enabled`) are deploy-time kill switches: they
        change only on redeploy and apply process-wide.
      - Runtime per-user/cohort toggles live in the DB-backed
        `feature_flag_service` (the `feature_flags` table), evaluated per
        request. Do not duplicate a flag across both systems.

    Secret aliases (e.g. `AUTH_JWT_SECRET`, `S3_APPLICATION_KEY`) are the
    deployed env-var / GitHub-secret names. Do NOT rename the `alias=` values:
    pydantic binds to the alias, so renaming silently drops the prod value.
    Required prod secrets are enforced fail-closed by `_require_prod_secrets`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ---
    database_url: str = Field(..., alias="DATABASE_URL")

    # --- Redis ---
    redis_url: str = Field(..., alias="REDIS_URL")

    # --- Auth ---
    session_cookie_name: str = Field(
        default="pycil-session", alias="SESSION_COOKIE_NAME"
    )
    auth_jwt_secret_current: str = Field(..., alias="AUTH_JWT_SECRET")
    auth_jwt_secret_previous: str | None = Field(
        default=None, alias="AUTH_JWT_SECRET_PREVIOUS"
    )
    internal_api_secret: str = Field(..., alias="INTERNAL_API_SECRET")
    jwt_max_age_seconds: int = Field(default=60 * 60 * 24 * 7, alias="JWT_MAX_AGE_SECONDS")

    # --- S3-compatible object storage (avatars + TTS audio) ---
    # MinIO locally, any S3 provider in prod. Distinct from the restic backup
    # service's Backblaze-native B2_ACCOUNT_* vars (a different API).
    s3_bucket: str | None = Field(default=None, alias="S3_BUCKET")
    s3_endpoint: str | None = Field(default=None, alias="S3_ENDPOINT")
    s3_key_id: str | None = Field(default=None, alias="S3_KEY_ID")
    s3_secret_key: str | None = Field(default=None, alias="S3_APPLICATION_KEY")
    s3_public_url_prefix: str | None = Field(default=None, alias="S3_PUBLIC_URL_PREFIX")

    # --- Stripe ---
    stripe_secret_key: str | None = Field(default=None, alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = Field(default=None, alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_id_pro: str | None = Field(default=None, alias="STRIPE_PRICE_ID_PRO")
    stripe_success_url: str | None = Field(default=None, alias="STRIPE_SUCCESS_URL")
    stripe_cancel_url: str | None = Field(default=None, alias="STRIPE_CANCEL_URL")
    enforce_tiers: bool = Field(default=False, alias="ENFORCE_TIERS")

    # --- Sentry / observability ---
    sentry_dsn_core: str | None = Field(default=None, alias="SENTRY_DSN_CORE")
    app_env: str = Field(default="dev", alias="APP_ENV")

    # --- OpenRouter LLM models ---
    # Precedence (do NOT rename these env vars — they are the deployed secret/
    # config names; see AUTH_JWT_SECRET note below):
    #   - Chat/streaming path resolves OPENROUTER_CHAT_MODEL first, then falls
    #     back to OPENROUTER_MODEL (llm_streaming.py).
    #   - Worker term/question generation uses OPENROUTER_MODEL directly.
    #   - LLM-judge grading uses its own LLM_JUDGE_MODEL.
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_model: str | None = Field(default=None, alias="OPENROUTER_MODEL")
    openrouter_chat_model: str | None = Field(default=None, alias="OPENROUTER_CHAT_MODEL")

    # --- LLM-as-judge tier-4 grading (default off) ---
    llm_judge_enabled: bool = Field(default=False, alias="LLM_JUDGE_ENABLED")
    llm_judge_model: str = Field(
        default="anthropic/claude-haiku-4-5", alias="LLM_JUDGE_MODEL"
    )
    llm_judge_per_user_daily_limit: int = Field(
        default=50, alias="LLM_JUDGE_PER_USER_DAILY_LIMIT"
    )
    llm_judge_budget_daily_usd: float = Field(
        default=1.0, alias="LLM_JUDGE_BUDGET_DAILY_USD"
    )

    # --- Question bank + prewarm ---
    question_bank_target_depth: int = Field(
        default=2, alias="QUESTION_BANK_TARGET_DEPTH"
    )
    question_bank_prewarm_enabled: bool = Field(
        default=True, alias="QUESTION_BANK_PREWARM_ENABLED"
    )
    question_bank_prewarm_types: str = Field(
        default="MULTIPLE_CHOICE", alias="QUESTION_BANK_PREWARM_TYPES"
    )

    @property
    def question_bank_prewarm_types_list(self) -> list[str]:
        return [t.strip() for t in self.question_bank_prewarm_types.split(",") if t.strip()]

    # --- CSRF / CORS ---
    allowed_origins: str = Field(default="http://localhost:3000", alias="ALLOWED_ORIGINS")

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @field_validator("allowed_origins")
    @classmethod
    def _reject_wildcard_origins(cls, v: str) -> str:
        for origin in (o.strip() for o in v.split(",") if o.strip()):
            if origin == "*" or "*" in origin or origin.lower() == "null":
                raise ValueError(
                    f"ALLOWED_ORIGINS rejects wildcards/null; got: {origin!r}"
                )
        return v

    @field_validator("app_env")
    @classmethod
    def _normalize_app_env(cls, v: str) -> str:
        return v.strip().lower()

    def _require_prod_secrets(self) -> "Settings":
        """Fail closed in prod: required external secrets must be set.

        DATABASE_URL / REDIS_URL / AUTH_JWT_SECRET / INTERNAL_API_SECRET are
        already required everywhere (no default). In prod we ALSO require the
        OpenRouter key + S3 storage so the app cannot boot half-configured and
        silently serve a degraded experience (no LLM, no avatar/TTS uploads).
        """
        if self.app_env != "prod":
            return self
        missing: list[str] = []
        if not self.openrouter_api_key:
            missing.append("OPENROUTER_API_KEY")
        if not self.s3_bucket:
            missing.append("S3_BUCKET")
        if not self.s3_secret_key:
            missing.append("S3_APPLICATION_KEY")
        if missing:
            raise ValueError(
                "prod boot rejected; required secrets unset: " + ", ".join(missing)
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()._require_prod_secrets()  # type: ignore[call-arg]
