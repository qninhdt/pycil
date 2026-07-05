"""Auth request/response DTOs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from pycil.auth.models import UserRole


class CurrentUser(BaseModel):
    id: UUID
    email: str
    name: str | None = None
    image: str | None = None
    role: UserRole = UserRole.user
    banned_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginStart(BaseModel):
    authorize_url: str
