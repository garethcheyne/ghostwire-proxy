from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default="user", nullable=False)  # admin, user
    is_active = Column(Boolean, default=True, nullable=False)
    signin_count = Column(Integer, default=0, nullable=False)
    last_signin_at = Column(DateTime(timezone=True), nullable=True)

    # TOTP two-factor auth. Mirrors LocalAuthUser so the admin portal and the
    # auth wall share one shape. Secret and backup codes are Fernet-encrypted;
    # totp_enabled only means "enrolment started", totp_verified means the user
    # proved they can generate a code — both must be true to challenge a login.
    totp_enabled = Column(Boolean, default=False, nullable=False)
    totp_verified = Column(Boolean, default=False, nullable=False)
    totp_secret = Column(Text, nullable=True)
    totp_backup_codes = Column(Text, nullable=True)  # encrypted JSON array
    totp_enrolled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
