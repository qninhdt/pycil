"""Runtime configuration (pydantic-settings).

Env-driven with dev defaults. Pycil owns the application schema and embeds the
Lexi domain library in the same PostgreSQL cluster under its own schema.
"""

from urllib.parse import urlsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REFRESH_COORDINATION_LOCK_TTL_SECONDS = 15
REFRESH_COORDINATION_WAIT_TIMEOUT_SECONDS = REFRESH_COORDINATION_LOCK_TTL_SECONDS + 1


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
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
    jwt_max_age_seconds: int = 900
    refresh_token_pepper: str = "changeme-refresh-token-pepper"
    refresh_token_ttl_seconds: int = Field(default=2_592_000, gt=0)
    # A bounded reuse interval lets concurrent callers recover the same successor
    # after a process/Redis failure without turning an old token into a permanent
    # credential. Reuse after this interval revokes the refresh family.
    refresh_token_replay_grace_seconds: int = Field(default=60, ge=32, le=300)
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
    centrifugo_public_sse_url: str = "https://localhost/connection/sse"
    centrifugo_subscribe_proxy_secret: str = "changeme-centrifugo-subscribe-proxy-secret"

    # --- generation safety ---------------------------------------------------
    word_generation_requests_per_hour: int = 5
    word_generation_max_inflight_per_user: int = 10
    word_generation_max_inflight_global: int = 500
    word_generation_daily_limit: int = 1_000

    # --- Embedded Lexi identity ----------------------------------------------
    # The fingerprint namespaces content work keys across immutable reference
    # dataset releases; it is not a service credential.
    lexi_reference_dataset_fingerprint: str = ""

    # --- assistant (isolated OpenAI-compatible provider + durable state) ----
    assistant_api_key: str = ""
    assistant_model: str = "gpt-4o-mini"
    assistant_base_url: str = ""
    assistant_reasoning_effort: str = ""
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

    @property
    def is_production(self) -> bool:
        """Whether this process is deployed, decided in exactly one place.

        Two guards turn on here — the deploy-time placeholder check and the refusal
        to mint a dev identity — and both used to compare `environment.lower()`
        against a set of their own. That made `ENVIRONMENT="production "`, an
        ordinary trailing space in an env file or a copied CI secret, silently
        *unset* production: placeholder secrets passed validation and the dev
        identity CLI would mint a token for any email. Stripping here fixes both,
        and having one property means a future third guard cannot disagree with
        these two.

        Deliberately still a denylist, and `is_development` below is the allowlist
        counterpart. The asymmetry is the point: this guard decides whether to
        *demand* real secrets, and demanding them from an unrecognised environment
        name would refuse to boot a deployment nobody meant to harden. The guard
        that hands out credentials cannot afford that latitude, so it asks the
        other question.
        """
        return self.environment.strip().lower() in {"production", "prod"}

    @property
    def is_development(self) -> bool:
        """Whether this process may mint a credential out of thin air.

        An allowlist, not the negation of `is_production`. Those differ for every
        name neither set mentions — `staging`, `preview`, `qa`, a typo — and the
        difference is that `is_production` answers "must secrets be real?" while
        this answers "may anyone with shell access become any learner?". A staging
        box holding real learners' data would answer no to the first and, under a
        denylist, yes to the second.

        So an unrecognised name gets development's *restrictions* rather than its
        latitude. Adding an environment is then a deliberate edit here, which is
        the failure mode worth having: a new name that cannot seed a local identity
        announces itself immediately, while one that silently can does not.
        """
        return self.environment.strip().lower() in {"development", "dev", "local", "test"}


def validate_production_settings(config: Settings) -> None:
    """Fail closed for deploy-time placeholders without impairing local tests.

    Development intentionally has convenient defaults; production must provide
    real secrets, exact browser origins, and an explicit OAuth callback allowlist.
    """
    if not config.is_production:
        return

    required = {
        "JWT_SECRET": config.jwt_secret,
        "DB_URL": config.db_url,
        "REFRESH_TOKEN_PEPPER": config.refresh_token_pepper,
        "REDIS_URL": config.redis_url,
        "INTERNAL_SECRET": config.internal_secret,
        "CENTRIFUGO_API_KEY": config.centrifugo_api_key,
        "CENTRIFUGO_TOKEN_HMAC_SECRET": config.centrifugo_token_hmac_secret,
        "CENTRIFUGO_SUBSCRIBE_PROXY_SECRET": config.centrifugo_subscribe_proxy_secret,
        "LEXI_REFERENCE_DATASET_FINGERPRINT": config.lexi_reference_dataset_fingerprint,
        "GOOGLE_CLIENT_ID": config.google_client_id,
        "GOOGLE_CLIENT_SECRET": config.google_client_secret,
    }
    placeholders = ("changeme", "replace-with", "redis-dev-only")
    unsafe = [
        name
        for name, value in required.items()
        if (
            not value
            or any(marker in value.lower() for marker in placeholders)
            or (
                name
                in {
                    "JWT_SECRET",
                    "REFRESH_TOKEN_PEPPER",
                    "INTERNAL_SECRET",
                    "CENTRIFUGO_API_KEY",
                    "CENTRIFUGO_TOKEN_HMAC_SECRET",
                    "CENTRIFUGO_SUBSCRIBE_PROXY_SECRET",
                }
                and len(value) < 32
            )
        )
    ]
    if config.jwt_secret_previous and (
        len(config.jwt_secret_previous) < 32
        or any(marker in config.jwt_secret_previous.lower() for marker in placeholders)
    ):
        unsafe.append("JWT_SECRET_PREVIOUS")
    if config.refresh_token_replay_grace_seconds <= REFRESH_COORDINATION_WAIT_TIMEOUT_SECONDS:
        unsafe.append("REFRESH_TOKEN_REPLAY_GRACE_SECONDS")
    if config.refresh_token_ttl_seconds <= 0:
        unsafe.append("REFRESH_TOKEN_TTL_SECONDS")
    if not _is_authenticated_redis_url(config.redis_url):
        unsafe.append("REDIS_URL")
    origins = config.cors_origins
    if not origins or any(
        origin == "*" or not _is_https_url(origin, origin=True) or "localhost" in origin.lower()
        for origin in origins
    ):
        unsafe.append("ALLOWED_ORIGINS")
    if not config.allowed_oauth_redirect_uris or any(
        not _is_https_url(uri) or "localhost" in uri.lower()
        for uri in config.allowed_oauth_redirect_uris
    ):
        unsafe.append("OAUTH_REDIRECT_URIS")
    if not config.domain or config.domain.lower() == "localhost":
        unsafe.append("DOMAIN")
    if (
        not _is_https_url(config.centrifugo_public_sse_url)
        or "localhost" in config.centrifugo_public_sse_url.lower()
    ):
        unsafe.append("CENTRIFUGO_PUBLIC_SSE_URL")
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
        if origin and (parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
            return False
    except ValueError:
        return False
    return True


def _is_authenticated_redis_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme.lower() in {"redis", "rediss"}
            and bool(parsed.hostname)
            and parsed.password is not None
            and bool(parsed.password)
        )
    except ValueError:
        return False


def get_settings() -> Settings:
    return Settings()


settings = get_settings()
