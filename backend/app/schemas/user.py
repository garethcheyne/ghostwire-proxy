from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

VALID_ROLES = ("admin", "user")


class UserBase(BaseModel):
    email: EmailStr
    name: str
    role: Literal["admin", "user"] = "user"

    @field_validator('email')
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        return v.lower()


class UserCreate(UserBase):
    password: str | None = None  # If None, generate random password


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    name: str | None = None
    role: Literal["admin", "user"] | None = None
    is_active: bool | None = None
    password: str | None = None

    @field_validator('email')
    @classmethod
    def email_lowercase(cls, v: str | None) -> str | None:
        return v.lower() if v else v


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    is_active: bool
    signin_count: int
    last_signin_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserCreateResponse(UserResponse):
    generated_password: str | None = None
