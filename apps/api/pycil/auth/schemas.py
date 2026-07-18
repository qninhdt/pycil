"""Auth request/response DTOs."""

from uuid import UUID

from pydantic import BaseModel


class CurrentUser(BaseModel):
    id: UUID
    email: str
    name: str | None = None
    image: str | None = None
    token_version: int = 0


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginStart(BaseModel):
    authorize_url: str


class CapabilitiesRead(BaseModel):
    assistant: bool
    realtime: bool = True
