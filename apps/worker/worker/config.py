"""Worker runtime config. Loaded from env."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = Field(..., alias="DATABASE_URL")
    redis_url: str = Field(..., alias="REDIS_URL")

    openrouter_api_key: str = Field(..., alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="openai/gpt-4o-mini", alias="OPENROUTER_MODEL"
    )
    openrouter_budget_daily_usd: float = Field(
        default=20.0, alias="OPENROUTER_BUDGET_DAILY_USD"
    )

    llm_timeout_seconds: float = 60.0
    job_timeout_seconds: int = 90


@lru_cache(maxsize=1)
def get_settings() -> WorkerSettings:
    return WorkerSettings()  # type: ignore[call-arg]
