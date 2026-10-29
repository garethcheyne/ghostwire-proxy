from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.schemas.proxy_host import _check_domain_names


class CertificateBase(BaseModel):
    name: str
    domain_names: list[str]

    # The names go to certbot as arguments and into /etc/letsencrypt/live/<name>/
    # paths, so they get the same check as a proxy host's server_name.
    @field_validator("domain_names")
    @classmethod
    def validate_domain_names(cls, v: list[str]) -> list[str]:
        return _check_domain_names(v)


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

    model_config = ConfigDict(from_attributes=True)
