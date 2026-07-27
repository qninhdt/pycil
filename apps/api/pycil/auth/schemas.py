"""Auth request/response DTOs.

Response DTOs carry ``serialization_alias`` so the wire is camelCase at the source.
The web client used to fix this up with a blanket recursive snake-to-camel transform
on every response body, which silently renamed fields nobody intended — and would
have nulled ``tokenVersion`` the moment that transform was deleted.

REQUEST DTOs deliberately keep their snake_case field names: ``refresh_token`` is
what clients already send, and renaming it would break callers for no gain.
"""

from uuid import UUID

from pydantic import BaseModel, Field


class CurrentUser(BaseModel):
    """The authenticated caller, as used INSIDE the API.

    ``token_version`` is the auth revocation counter, checked when minting a
    realtime connection token and when authorizing an assistant run. It is server
    state and is not part of any response body — see ``ViewerRead``.
    """

    id: UUID
    email: str
    name: str | None = None
    image: str | None = None
    token_version: int = 0


class ViewerRead(BaseModel):
    """The ``GET /v1/me`` projection.

    Exists so ``token_version`` cannot reach the browser. It was previously served
    because ``CurrentUser`` doubled as the response model, which meant the
    revocation counter shipped to every client that asked who it was.
    """

    id: UUID
    email: str
    name: str | None = None
    image: str | None = None


class TokenResponse(BaseModel):
    access_token: str = Field(serialization_alias="accessToken")
    refresh_token: str = Field(serialization_alias="refreshToken")
    token_type: str = Field(default="bearer", serialization_alias="tokenType")
    expires_in: int = Field(serialization_alias="expiresIn")
    refresh_expires_in: int = Field(serialization_alias="refreshExpiresIn")


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class LoginStart(BaseModel):
    authorize_url: str = Field(serialization_alias="authorizeUrl")


class CapabilitiesRead(BaseModel):
    assistant: bool
    realtime: bool = True
