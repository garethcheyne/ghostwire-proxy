"""API keys: how scripts and AI agents (over MCP) call the API without a browser session.

A key is `gwp_<prefix>_<secret>`. Only the prefix (to find the row and to show in the UI) and a
SHA-256 hash of the whole key are stored; the key itself is shown once, when it is created.
"""
from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, DateTime, JSON, String

from app.core.database import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    # The public part of the key, unique, used to look the row up. Safe to display.
    prefix = Column(String(16), nullable=False, unique=True, index=True)
    # SHA-256 (hex) of the full key. The secret has ~238 bits of entropy, so a slow
    # password hash would add latency to every request without adding safety.
    hash = Column(String(64), nullable=False)
    scopes = Column(JSON, nullable=False, default=list)

    # The admin who created it; the key acts with that user's identity and stops
    # working if the user is disabled or loses the admin role.
    created_by = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    last_used_ip = Column(String(45), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    # Revoking keeps the row (soft delete) so the audit trail can still name the key.
    revoked_at = Column(DateTime(timezone=True), nullable=True)
