from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.user import UserRead


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AuthSessionResponse(BaseModel):
    """A freshly issued bearer session. The token is returned exactly once —
    only its hash is stored server-side."""

    token: str
    user: UserRead
