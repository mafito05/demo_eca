from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.auth.models import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    specialty: str | None
    institution: str | None
    is_demo: bool


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(max_length=160)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.trainee
    specialty: str | None = None
    institution: str | None = None
