"""Request and response payloads for account lifecycle operations."""

from pydantic import BaseModel, Field


class AccountDeleteRequest(BaseModel):
    refresh_token: str = Field(min_length=1)
    confirmation: str


class AccountExport(BaseModel):
    profile: dict
    hierarchy: list[dict]
    learning: dict
    word_generations: list[dict]
    assistant: dict
