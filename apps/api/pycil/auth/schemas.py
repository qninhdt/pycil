"""Auth request/response DTOs.

Response DTOs carry ``serialization_alias`` so the wire is camelCase at the
source. The web client used to fix this up with a blanket recursive snake-to-camel
transform on every response body, which silently renamed fields nobody intended.
"""

from uuid import UUID

from pydantic import BaseModel


class CurrentUser(BaseModel):
    """The authenticated caller, as used INSIDE the API.

    Identity only: the internal UUID every authorization decision keys on, plus
    the profile fields a route may echo. There is deliberately no session or
    credential state here — Clerk owns sessions, and a Pycil-side revocation
    counter was removed with the rest of the custom auth stack.
    """

    id: UUID
    email: str
    name: str | None = None
    image: str | None = None


class ViewerRead(BaseModel):
    """The ``GET /v1/me`` projection."""

    id: UUID
    email: str
    name: str | None = None
    image: str | None = None


class CapabilitiesRead(BaseModel):
    assistant: bool
