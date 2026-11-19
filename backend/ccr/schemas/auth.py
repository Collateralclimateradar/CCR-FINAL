"""Data shapes for login."""
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Email = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=320)]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    # Upper limit stops oversized passwords from being used to slow the server down.
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # seconds


class CurrentUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    full_name: str
    role: str
