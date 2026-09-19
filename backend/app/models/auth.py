"""Better Auth's tables for admin sign-in.

The admin UI (Next.js) runs Better Auth, which owns sign-in, sessions and passwords. Its user
table is our `users` table; these hold its sessions, credentials and one-time tokens. The API
only reads sessions (see app/api/deps.py) and writes credentials when admins manage users.
Column names follow the field mapping in frontend/src/lib/auth.ts.
"""
from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, DateTime, String, Text

from app.core.database import Base


def _now():
    return datetime.now(timezone.utc)


class AuthSession(Base):
    __tablename__ = "auth_session"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    token = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    ip_address = Column(String(255), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class AuthAccount(Base):
    """A way to sign in. provider_id 'credential' holds the bcrypt password hash."""

    __tablename__ = "auth_account"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    account_id = Column(String(255), nullable=False)
    provider_id = Column(String(255), nullable=False)
    password = Column(Text, nullable=True)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    id_token = Column(Text, nullable=True)
    access_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    refresh_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    scope = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class AuthVerification(Base):
    __tablename__ = "auth_verification"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    identifier = Column(String(255), nullable=False, index=True)
    value = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
