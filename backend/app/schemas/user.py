from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime
from typing import Literal, Optional

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
    password: Optional[str] = None  # If None, generate random password


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    role: Optional[Literal["admin", "user"]] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

    @field_validator('email')
    @classmethod
    def email_lowercase(cls, v: Optional[str]) -> Optional[str]:
        return v.lower() if v else v


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    is_active: bool
    signin_count: int
    last_signin_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserCreateResponse(UserResponse):
    generated_password: Optional[str] = None
