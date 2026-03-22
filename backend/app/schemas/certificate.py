from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class CertificateBase(BaseModel):
    name: str
    domain_names: list[str]


class CertificateCreate(CertificateBase):
    pass


class CertificateUpload(CertificateBase):
    certificate: str  # PEM format
    certificate_key: str  # PEM format
    certificate_chain: Optional[str] = None  # PEM format


class CertificateLetsEncrypt(CertificateBase):
    email: EmailStr


class CertificateResponse(BaseModel):
    id: str
    name: str
    domain_names: list[str]

    is_letsencrypt: bool
    letsencrypt_email: Optional[str]

    expires_at: Optional[datetime]
    auto_renew: bool

    status: str
    last_renewed_at: Optional[datetime]
    error_message: Optional[str]

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
