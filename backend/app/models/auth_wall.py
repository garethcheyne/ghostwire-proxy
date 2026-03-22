from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class AuthWall(Base):
    __tablename__ = "auth_walls"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)

    # Auth type: 'basic', 'oauth', 'ldap', 'multi'
    auth_type = Column(String(20), default="basic", nullable=False)

    # Session configuration
    session_timeout = Column(Integer, default=3600, nullable=False)  # seconds

    # Auth portal theme (directory name in frontend-authwall/)
    theme = Column(String(100), default="default", nullable=False)

    # Optional: Default provider for OAuth
    default_provider_id = Column(String(36), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    proxy_hosts = relationship("ProxyHost", back_populates="auth_wall")
    local_users = relationship("LocalAuthUser", back_populates="auth_wall", cascade="all, delete-orphan")
    auth_providers = relationship("AuthProvider", back_populates="auth_wall", cascade="all, delete-orphan")
    ldap_configs = relationship("LdapConfig", back_populates="auth_wall", cascade="all, delete-orphan")


class LocalAuthUser(Base):
    """Basic auth users for auth walls with optional TOTP support"""
    __tablename__ = "local_auth_users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    auth_wall_id = Column(String(36), ForeignKey("auth_walls.id", ondelete="CASCADE"), nullable=False, index=True)

    username = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)

    # Optional info
    display_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # TOTP (Two-Factor Authentication)
    totp_enabled = Column(Boolean, default=False, nullable=False)
    totp_secret = Column(Text, nullable=True)  # Encrypted with Fernet
    totp_verified = Column(Boolean, default=False, nullable=False)  # Has user verified TOTP setup?
    totp_backup_codes = Column(Text, nullable=True)  # Encrypted JSON array of backup codes

    # Security: Failed login tracking
    failed_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_failed_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    auth_wall = relationship("AuthWall", back_populates="local_users")

    def is_locked(self) -> bool:
        """Check if account is currently locked."""
        if self.locked_until is None:
            return False
        return datetime.now(timezone.utc) < self.locked_until


class AuthProvider(Base):
    """OAuth/SSO providers for auth walls"""
    __tablename__ = "auth_providers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    auth_wall_id = Column(String(36), ForeignKey("auth_walls.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(255), nullable=False)

    # Provider type: 'google', 'github', 'azure_ad', 'oidc'
    provider_type = Column(String(50), nullable=False)

    # OAuth configuration
    client_id = Column(String(255), nullable=True)
    client_secret = Column(Text, nullable=True)  # Encrypted

    # OIDC URLs (for custom OIDC providers)
    authorization_url = Column(String(500), nullable=True)
    token_url = Column(String(500), nullable=True)
    userinfo_url = Column(String(500), nullable=True)

    # Scopes
    scopes = Column(String(500), default="openid email profile", nullable=False)

    # Status
    enabled = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    auth_wall = relationship("AuthWall", back_populates="auth_providers")


class LdapConfig(Base):
    """LDAP configuration for auth walls"""
    __tablename__ = "ldap_configs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    auth_wall_id = Column(String(36), ForeignKey("auth_walls.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(255), nullable=False)

    # Server configuration
    host = Column(String(255), nullable=False)
    port = Column(Integer, default=389, nullable=False)
    use_ssl = Column(Boolean, default=False, nullable=False)
    use_starttls = Column(Boolean, default=False, nullable=False)

    # Bind credentials
    bind_dn = Column(String(500), nullable=True)
    bind_password = Column(Text, nullable=True)  # Encrypted

    # Search configuration
    base_dn = Column(String(500), nullable=False)
    user_filter = Column(String(500), default="(uid=%s)", nullable=False)

    # Attribute mapping
    username_attribute = Column(String(100), default="uid", nullable=False)
    email_attribute = Column(String(100), default="mail", nullable=True)
    display_name_attribute = Column(String(100), default="cn", nullable=True)

    # Status
    enabled = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    auth_wall = relationship("AuthWall", back_populates="ldap_configs")
