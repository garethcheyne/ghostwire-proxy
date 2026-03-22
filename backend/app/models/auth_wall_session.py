"""
Auth Wall Session model for server-side session management.
Sessions are stored in the database for instant revocation capability.
"""
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import secrets

from app.core.database import Base


def generate_session_id() -> str:
    """Generate a cryptographically secure session ID."""
    return secrets.token_hex(32)  # 64 character hex string


class AuthWallSession(Base):
    """Server-side session for auth wall authentication."""
    __tablename__ = "auth_wall_sessions"

    # Primary key - cryptographically secure random ID
    id = Column(String(64), primary_key=True, default=generate_session_id)

    # Auth wall this session belongs to
    auth_wall_id = Column(
        String(36),
        ForeignKey("auth_walls.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # User identity
    user_type = Column(String(20), nullable=False)  # 'local', 'google', 'github', 'oidc', 'ldap'
    user_id = Column(String(255), nullable=False)   # LocalAuthUser.id or external user ID
    username = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    display_name = Column(String(255), nullable=True)

    # Provider reference (for OAuth sessions)
    provider_id = Column(String(36), nullable=True)  # AuthProvider.id

    # Client metadata
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(500), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )
    last_activity_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Revocation
    revoked = Column(Boolean, default=False, nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_reason = Column(String(255), nullable=True)

    # Relationships
    auth_wall = relationship("AuthWall", backref="sessions")

    # Composite indexes for efficient queries
    __table_args__ = (
        Index('ix_sessions_wall_user', 'auth_wall_id', 'user_id'),
        Index('ix_sessions_valid', 'auth_wall_id', 'revoked', 'expires_at'),
    )

    def is_valid(self) -> bool:
        """Check if session is currently valid."""
        if self.revoked:
            return False
        if datetime.now(timezone.utc) > self.expires_at:
            return False
        return True

    def to_cache_dict(self) -> dict:
        """Convert to dictionary for Lua cache storage."""
        return {
            "session_id": self.id,
            "auth_wall_id": self.auth_wall_id,
            "user_type": self.user_type,
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "expires_at": int(self.expires_at.timestamp()),
            "valid": self.is_valid(),
        }
