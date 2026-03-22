from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class AccessList(Base):
    __tablename__ = "access_lists"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)

    # Mode: 'whitelist' (allow only listed) or 'blacklist' (block listed)
    mode = Column(String(20), default="blacklist", nullable=False)

    # Default action for IPs not in list
    default_action = Column(String(20), default="allow", nullable=False)  # allow, deny

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    entries = relationship("AccessListEntry", back_populates="access_list", cascade="all, delete-orphan")
    proxy_hosts = relationship("ProxyHost", back_populates="access_list")


class AccessListEntry(Base):
    __tablename__ = "access_list_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    access_list_id = Column(String(36), ForeignKey("access_lists.id", ondelete="CASCADE"), nullable=False, index=True)

    # IP address or CIDR notation
    ip_or_cidr = Column(String(50), nullable=False)

    # Action: 'allow' or 'deny'
    action = Column(String(20), default="deny", nullable=False)

    # Optional description
    description = Column(String(255), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    access_list = relationship("AccessList", back_populates="entries")
