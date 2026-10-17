"""Process environment settings, validated before resource creation."""

import os
from typing import ClassVar, Self
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, SecretStr, field_validator, model_validator
from sqlalchemy.engine import make_url

from pycil.observability.config import TelemetrySettings


class ProcessSettings(TelemetrySettings):
    model_config = ConfigDict(extra="forbid", frozen=True)
    db_url: SecretStr
    redis_url: SecretStr
    llm_api_key: SecretStr
    llm_base_url: str

    @model_validator(mode="after")
    def validate_addresses(self) -> Self:
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
        self.validate_service_urls(self.llm_base_url)
        return self

    @staticmethod
    def validate_service_urls(*values: str) -> None:
        for value in values:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("service URLs must be HTTP(S) without embedded credentials")

    environment_names: ClassVar[dict[str, str]] = {
        "otel_endpoint": "OTEL_EXPORTER_OTLP_ENDPOINT",
        "otel_sample_ratio": "OTEL_TRACES_SAMPLER_ARG",
    }

    @classmethod
    def from_environment(cls) -> Self:
        values = {
            name: os.getenv(cls.environment_names.get(name, name.upper()))
            for name in cls.model_fields
        }
        missing = [
            cls.environment_names.get(name, name.upper())
            for name, field in cls.model_fields.items()
            if field.is_required() and not (values[name] or "").strip()
        ]
        if missing:
            raise ValueError("Missing deployment variables: " + ", ".join(sorted(missing)))
        try:
            provided: dict[str, object] = {name: value for name, value in values.items() if value}
            return cls.model_validate(provided)
        except ValueError, TypeError:
            # Validation errors may embed raw input, including database passwords.
            raise ValueError(
                "Invalid deployment configuration; check environment addresses"
            ) from None


class WorkerSettings(ProcessSettings):
    otel_service_name: str = Field(default="pycil-worker", min_length=1)


class ApiSettings(ProcessSettings):
    clerk_jwks_url: str
    clerk_issuer: str
    clerk_audience: str | None = None
    clerk_secret_key: SecretStr
    allowed_origins: list[str] = Field(default_factory=list)
    decision_api_key: SecretStr
    decision_base_url: str
    search_index_path: str | None = None
    otel_service_name: str = Field(default="pycil-api", min_length=1)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def validate_api_addresses(self) -> Self:
        self.validate_service_urls(self.clerk_jwks_url, self.clerk_issuer, self.decision_base_url)
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
