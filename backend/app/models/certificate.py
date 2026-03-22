from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)

    # Domain names this certificate covers
    domain_names = Column(JSON, nullable=False)  # List of domains

    # Certificate data (PEM format)
    certificate = Column(Text, nullable=True)  # Public cert
    certificate_key = Column(Text, nullable=True)  # Private key (encrypted)
    certificate_chain = Column(Text, nullable=True)  # Intermediate certs

    # Let's Encrypt
    is_letsencrypt = Column(Boolean, default=False, nullable=False)
    letsencrypt_email = Column(String(255), nullable=True)

    # Expiration
    expires_at = Column(DateTime(timezone=True), nullable=True)
    auto_renew = Column(Boolean, default=True, nullable=False)

    # Status
    status = Column(String(50), default="pending", nullable=False)  # pending, valid, expired, error
    last_renewed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    proxy_hosts = relationship("ProxyHost", back_populates="certificate")
