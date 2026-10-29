from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str]
    # None = never expires
    expires_in_days: int | None = Field(default=90, ge=1, le=3650)
    # A current code from the admin's authenticator app (or a backup code): creating a key is
    # a step-up action, like disabling two-factor.
    code: str = Field(min_length=6, max_length=16)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    prefix: str
    display: str  # "gwp_<prefix>_…"
    scopes: list[str]
    created_by: str
    created_by_email: str | None = None
    created_at: datetime
    last_used_at: datetime | None = None
    last_used_ip: str | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    status: str  # active, expired, revoked


class ApiKeyCreated(ApiKeyResponse):
    # The full key. Returned once, here, and never again.
    key: str


class ApiKeyScope(BaseModel):
    name: str
    description: str
