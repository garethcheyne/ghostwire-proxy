from datetime import datetime

from pydantic import BaseModel, EmailStr


class CertificateBase(BaseModel):
    name: str
    domain_names: list[str]


class CertificateCreate(CertificateBase):
    pass


class CertificateUpload(CertificateBase):
    certificate: str  # PEM format
    certificate_key: str  # PEM format
    certificate_chain: str | None = None  # PEM format


class CertificateLetsEncrypt(CertificateBase):
    email: EmailStr


class CertificateResponse(BaseModel):
    id: str
    name: str
    domain_names: list[str]

    is_letsencrypt: bool
    letsencrypt_email: str | None

    expires_at: datetime | None
    auto_renew: bool

    status: str
    last_renewed_at: datetime | None
    error_message: str | None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
