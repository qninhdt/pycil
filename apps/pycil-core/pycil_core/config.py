from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Pycil-core runtime config. Loaded from env or .env file."""

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

    # --- B2 / S3-compatible storage (avatars + TTS) ---
    b2_bucket: str | None = Field(default=None, alias="B2_BUCKET")
    b2_endpoint: str | None = Field(default=None, alias="B2_ENDPOINT")
    b2_key_id: str | None = Field(default=None, alias="B2_KEY_ID")
    b2_application_key: str | None = Field(default=None, alias="B2_APPLICATION_KEY")
    b2_public_url_prefix: str | None = Field(default=None, alias="B2_PUBLIC_URL_PREFIX")

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
