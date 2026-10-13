"""Deployment addresses and secrets, validated before resource creation."""

import os
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, SecretStr, model_validator
from sqlalchemy.engine import make_url


class Deployment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    db_url: SecretStr
    redis_url: SecretStr
    clerk_jwks_url: str
    clerk_issuer: str
    clerk_audience: str | None
    clerk_secret_key: SecretStr
    allowed_origins: list[str]
    llm_api_key: SecretStr
    llm_base_url: str
    decision_api_key: SecretStr
    decision_base_url: str
    search_index_path: str | None = None

    @model_validator(mode="after")
    def validate_addresses(self):
        try:
            database = make_url(self.db_url.get_secret_value())
        except Exception:
            raise ValueError("invalid database address") from None
        if (
            database.drivername != "postgresql+asyncpg"
            or not database.database
            or not database.host
        ):
            raise ValueError("DB_URL must identify a PostgreSQL application database")
        redis = urlsplit(self.redis_url.get_secret_value())
        if redis.scheme not in {"redis", "rediss"} or not redis.hostname:
            raise ValueError("REDIS_URL must identify a Redis server")
        for value in (
            self.clerk_jwks_url,
            self.clerk_issuer,
            self.llm_base_url,
            self.decision_base_url,
        ):
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("service URLs must be HTTP(S) without embedded credentials")
        for value in self.allowed_origins:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("ALLOWED_ORIGINS must contain explicit HTTP(S) origins")
        return self

    @classmethod
    def from_environment(cls):
        required = {
            "db_url": "DB_URL",
            "redis_url": "REDIS_URL",
            "clerk_jwks_url": "CLERK_JWKS_URL",
            "clerk_issuer": "CLERK_ISSUER",
            "clerk_secret_key": "CLERK_SECRET_KEY",
            "llm_api_key": "LLM_API_KEY",
            "llm_base_url": "LLM_BASE_URL",
            "decision_api_key": "DECISION_API_KEY",
            "decision_base_url": "DECISION_BASE_URL",
        }
        missing = [key for key in required.values() if not os.getenv(key, "").strip()]
        if missing:
            raise ValueError("Missing deployment variables: " + ", ".join(sorted(missing)))
        try:
            return cls(
                db_url=SecretStr(os.environ["DB_URL"]),
                redis_url=SecretStr(os.environ["REDIS_URL"]),
                clerk_jwks_url=os.environ["CLERK_JWKS_URL"],
                clerk_issuer=os.environ["CLERK_ISSUER"],
                clerk_audience=os.getenv("CLERK_AUDIENCE") or None,
                clerk_secret_key=SecretStr(os.environ["CLERK_SECRET_KEY"]),
                allowed_origins=[
                    s.strip() for s in os.environ.get("ALLOWED_ORIGINS", "").split(",") if s.strip()
                ],
                llm_api_key=SecretStr(os.environ["LLM_API_KEY"]),
                llm_base_url=os.environ["LLM_BASE_URL"],
                decision_api_key=SecretStr(os.environ["DECISION_API_KEY"]),
                decision_base_url=os.environ["DECISION_BASE_URL"],
                search_index_path=os.getenv("SEARCH_INDEX_PATH") or None,
            )
        except ValueError, TypeError:
            # Validation errors may embed raw input, including database passwords.
            raise ValueError(
                "Invalid deployment configuration; check environment addresses"
            ) from None
