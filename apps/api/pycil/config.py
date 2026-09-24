"""Runtime configuration (pydantic-settings).

Env-driven with dev defaults. Pycil owns the application schema and embeds the
Lexi domain library in the same PostgreSQL cluster under its own schema.
"""

from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # --- auth (Clerk) --------------------------------------------------------
    # Clerk issues and validates sessions; Pycil verifies the bearer token against
    # Clerk's JWKS and maps the subject to an internal UUID. There is no local
    # signing secret, so nothing here can mint a credential.
    clerk_secret_key: str = ""
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    clerk_audience: str = ""
    internal_secret: str = "changeme-base64-32-bytes"

    # --- CORS / origins ------------------------------------------------------
    allowed_origins: str = "http://localhost,https://localhost"
    max_body_bytes: int = 1_048_576

    # --- Embedded Lexi identity ----------------------------------------------
    # The fingerprint namespaces content work keys across immutable reference
    # dataset releases; it is not a service credential.
    lexi_reference_dataset_fingerprint: str = ""

    # --- assistant (isolated OpenAI-compatible provider + durable state) ----
    # Connection and credential only. The model, its reasoning effort and the
    # turn budget are product policy and live in config/config.yaml, so a model
    # or budget change is a config edit rather than a redeploy of environment
    # values across every replica.
    assistant_api_key: str = ""
    assistant_base_url: str = ""
    assistant_checkpoint_db_url: str = ""
    assistant_run_deadline_seconds: int = 120
    assistant_max_message_chars: int = 8000
    # Fallback window for a model whose catalog entry is unavailable. The
    # catalog's own per-model ``context_window`` is what normally bounds a
    # request; this only covers the case where no entry can be resolved.
    assistant_context_window_tokens: int = 8_192
    # Concurrent runs per learner are bounded by plan (account.plans), not here.
    assistant_retention_days: int = 30

    @property
    def assistant_psycopg_url(self) -> str:
        """Dedicated psycopg URL; never pass SQLAlchemy's asyncpg DSN to LangGraph."""
        configured = self.assistant_checkpoint_db_url or self.db_url
        return configured.replace("postgresql+asyncpg://", "postgresql://", 1)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

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

        Deliberately a denylist rather than an allowlist: this guard decides whether
        to *demand* real secrets, and demanding them from an unrecognised environment
        name would refuse to boot a deployment nobody meant to harden.
        """
        return self.environment.strip().lower() in {"production", "prod"}


def validate_production_settings(config: Settings) -> None:
    """Fail closed for deploy-time placeholders without impairing local tests.

    Development intentionally has convenient defaults; production must provide
    real secrets and exact browser origins. Clerk credentials are deliberately not
    required here: the JWKS URL and issuer are what verification needs, and a
    deployment that only *verifies* tokens (never calls the Clerk management API)
    is legitimate. The verifier itself refuses to run unconfigured.
    """
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
        if (
            not value
            or any(marker in value.lower() for marker in placeholders)
            or (name == "INTERNAL_SECRET" and len(value) < 32)
        )
    ]
    if not _is_authenticated_redis_url(config.redis_url):
        unsafe.append("REDIS_URL")
    origins = config.cors_origins
    if not origins or any(
        origin == "*" or not _is_https_url(origin, origin=True) or "localhost" in origin.lower()
        for origin in origins
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
